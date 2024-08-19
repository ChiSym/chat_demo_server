from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from jinja2_fragments.fastapi import Jinja2Blocks
from typing import Annotated, Callable

import ipdb
import json
import logging as log
import requests
import traceback

from .chat_demo_server import ChatDemoServer


log.getLogger().setLevel(log.DEBUG)
log.getLogger("jax").setLevel(log.WARNING)
log.getLogger("asyncio").setLevel(log.WARNING)
log.getLogger("multipart.multipart").setLevel(log.WARNING)


templates = Jinja2Blocks(directory="src")

genfact_server = '34.44.35.203'
genfact_server_port = 8888

physician_fields = [
    "first",
	"last",
    "specialty", 
    "npi",
    "school",
	"degree"
    ]
business_fields = [
    "legal_name",
    "addr",
    "addr2",
    "city",
    "zip",
    ]
joint_fields = physician_fields + business_fields


async def query1_callback(request: Request, english_query: str, query_counter):
    genfact_url = f"http://{genfact_server}:{genfact_server_port}/sentence-to-doctor-data"

    try:
        response = requests.post(genfact_url, 
                                 json={"sentence": english_query},
                                 timeout=90.0)

        log.debug(f"GenFact response: {response.json()}")

        entities = [{'entity_html': k, 'pval': v['likelihood'], **v} for k, v in response.json()['posterior'].items()]
        for entity in entities:
            if 'as_object' in entity:
                entity['as_object'] = {k: v for k, v in entity['as_object'].items() if v != 'NONE'}
        entities.sort(key=lambda x: x['pval'], reverse=True)

        return templates.TemplateResponse(
            "index.html.jinja",
            {"request": request, 
            "idnum": next(query_counter),
            "ml_entity": entities[0],
            "genfact_entities": entities},
            block_name="query2",
        )
        
    except Exception as e:
        log.error(f"Error in GenParse on English query (\"{english_query}\") : {e}")
        return templates.TemplateResponse(
            "index.html.jinja",
            {"request": request, 
             "idnum": next(query_counter),
             "ml_entity": None,
             "genfact_entities": [],
             "error": f"{e}"
             },
            block_name="query2")
    

async def query2_callback(request: Request, query_counter, **kwargs):
    log.debug(f"Received kwargs: {kwargs}")
    if int(kwargs.get("dummy", 0)) == 1:
        return post_pclean_dummy(request, query_counter)
    
    try:
        english_query = kwargs.get('english_query')
        genfact_entity = kwargs.get('genfact_entity')
        genfact_url = f"http://{genfact_server}:{genfact_server_port}/run-pclean"

        genfact_entity_dict = json.loads(genfact_entity)
        pclean_payload = {"observations": genfact_entity_dict}
        if 'c2z3' in pclean_payload['observations']:
            del pclean_payload['observations']['c2z3']

        response = requests.post(genfact_url, json=pclean_payload, timeout=90.0)
        pclean_resp = response.json()

        return pclean_row_response(pclean_resp=pclean_resp, request=request, english_query=english_query, genfact_entity=genfact_entity, query_counter=query_counter)
    
    except Exception as e:
        log.error(f"Error running pclean for genfact_entity (\"{genfact_entity}\") : {e}")
        traceback.print_exception(e)
        return templates.TemplateResponse(
            "index.html.jinja",
            {"request": request, 
             "idnum": next(query_counter),
             "genfact_entity": genfact_entity,
             "error": f"{e}"
             },
            block_name="plot")
    


# Create and setup the server
server = ChatDemoServer(templates, query1_callback, query2_callback)
server.setup_routes() # Create the default routes
app = server.get_app() # Expose the app for uvicorn CLI


def pclean_row_response(*, pclean_resp: dict, request, english_query, genfact_entity, query_counter):
    log.debug(f"pclean response: {pclean_resp}")

    docs, biz, doc_keys, biz_keys = extract_docs_and_biz(pclean_resp).values()
    
    # Add any extra fields to the end of the standard list
    doc_keys = physician_fields + list(doc_keys - set(physician_fields))
    biz_keys = business_fields + list(biz_keys - set(business_fields))
    
    joint, joint_keys = extract_joint(pclean_resp).values()
    joint_keys = joint_fields + list(joint_keys - set(joint_fields))

    return templates.TemplateResponse(
        "index.html.jinja",
        {"request": request, 
        "idnum": next(query_counter),
        "physician_fields": physician_fields,
        "business_fields": business_fields,
        "joint_fields": joint_fields,
        "english_query": english_query,
        "genfact_entity": genfact_entity,
        "docs": docs,
        "biz": biz,
        "joint": joint,
        "doc_keys": doc_keys,
        "biz_keys": biz_keys,
        "joint_keys": joint_keys
        },
        block_name="plot")

def extract_entities(pclean_entities: list) -> list:
    entities = []
    ent_keys = set()
    # log.debug(f"entities: {pclean_entities}")

    for ent in pclean_entities:
        if "entity" in ent and isinstance(ent["entity"], dict):
            for key, value in ent["entity"].items():
                ent[key] = value
            del ent["entity"]
        ent_keys |= set(ent.keys())
        ent["new_entity"] = False
        entities.append(ent)

    return entities, ent_keys - {"id", "count"}

def extract_docs_and_biz(pclean_result: dict) -> dict:
    # log.debug(f"pclean result keys: {pclean_result.keys()}")

    doc_count = pclean_result["physician_count"]
    biz_count = pclean_result["businesses_count"]

    bizs, biz_keys = extract_entities(pclean_result["businesses"])
    docs, doc_keys = extract_entities(pclean_result["physicians"])

    if doc_count > 0:
        docs.append({"count": pclean_result["physician_new_entity"], "new_entity": True})

        # Sort the dicts' values by the "count" field for the histograms
        docs = sorted(docs, key=lambda x: x["count"], reverse=True)
        normalize_counts(doc_count, docs)

    if biz_count > 0:
        bizs.append({"count": pclean_result["business_new_entity"], "new_entity": True})

        # Sort the dicts' values by the "count" field for the histograms
        bizs = sorted(bizs, key=lambda x: x["count"], reverse=True)
        normalize_counts(biz_count, bizs)

    return {"docs": docs, "biz": bizs, "doc_keys": doc_keys, "biz_keys": biz_keys}


def extract_joint(pclean_result: dict) -> dict:
    joint_ents = pclean_result["joint"]
    joint_count = pclean_result["joint_count"]

    joint_keys = set()
    joint = []

    for ent in joint_ents:
        for ent_key in ["physician", "business"]:
            if ent_key in ent and isinstance(ent[ent_key], dict):
                for key, value in ent[ent_key].items():
                    ent[key] = ent[ent_key][key] # requires no overlapping keys
                del ent[ent_key]
        joint_keys |= set(ent.keys())
        ent["doc_new_ent"] = ent["id"][0] == "new_entity"
        ent["biz_new_ent"] = ent["id"][1] == "new_entity"
        joint.append(ent)

    # log.debug(f"joint: {joint}")
    joint_keys -= {"id", "count", "doc_new_ent", "biz_new_ent"}
    # log.debug(f"joint_keys: {joint_keys}")

    sorted_joint = sorted(joint, key=lambda x: x["count"], reverse=True)
    normalize_counts(joint_count, sorted_joint)
    log.debug(f"joint: {sorted_joint}")

    return {"joint": sorted_joint, "joint_keys": joint_keys}


def normalize_counts(cnt: int, entities: list) -> None:
    if cnt > 0:
        for ent in entities:
            ent["proportion"] = ent["count"] / cnt
    elif len(entities) > 0:
        log.error(f"Count is zero but we need to normalize {entities}")
        raise ValueError("Count is zero but there are entities to normalize")



def post_pclean_dummy(request: Request, query_counter, empty: bool = False):
    if empty:
        pclean_resp = {
            "businesses_count": 1000,
            "business_histogram": {},
            "physician_new_entity": 1000,
            "physicians": [],
            "businesses": [],
            "count": 1000,
            "business_new_entity": 1000,
            "results": [],
            "physician_count": 1000,
            "physician_histogram": {}
        }
    else:
        pclean_resp = {
            "physician_new_entity": 1,
            "business_new_entity": 0,
            "joint_count": 2000,
            "physician_count": 2000,
            "businesses_count": 2000,
            "joint": [{
                "id": ["row_7742", "row_88049"],
                "count": 230,
                "physician": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                },
                "business": {
                    "addr": "431 N 21ST ST",
                    "addr2": "",
                    "city": "CAMP HILL",
                    "zip": "170112202",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": ["row_7742", "row_88742"],
                "count": 245,
                "physician": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                },
                "business": {
                    "addr": "1211 FORGE RD",
                    "addr2": "",
                    "city": "CARLISLE",
                    "zip": "170133183",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": ["row_7742", "row_86727"],
                "count": 258,
                "physician": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                },
                "business": {
                    "addr": "429 N 21ST ST",
                    "addr2": "",
                    "city": "CAMP HILL",
                    "zip": "170112202",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": ["row_7742", "row_89758"],
                "count": 249,
                "physician": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                },
                "business": {
                    "addr": "126 W CHURCH ST",
                    "addr2": "",
                    "city": "DILLSBURG",
                    "zip": "170191280",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": ["row_7742", "row_90125"],
                "count": 225,
                "physician": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                },
                "business": {
                    "addr": "20 CAPITAL DR",
                    "addr2": "",
                    "city": "HARRISBURG",
                    "zip": "171109446",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": ["row_7742", "row_90094"],
                "count": 285,
                "physician": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                },
                "business": {
                    "addr": "2313 OAKFIELD RD",
                    "addr2": "",
                    "city": "ARLINGTON",
                    "zip": "189762010",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": ["new_entity", "row_88742"],
                "count": 1,
                "business": {
                    "addr": "1211 FORGE RD",
                    "addr2": "",
                    "city": "CARLISLE",
                    "zip": "170133183",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": ["row_7742", "row_90767"],
                "count": 256,
                "physician": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                },
                "business": {
                    "addr": "4665 E TRINDLE RD",
                    "addr2": "",
                    "city": "MECHANICSBURG",
                    "zip": "170503640",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": ["row_7742", "row_91720"],
                "count": 251,
                "physician": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                },
                "business": {
                    "addr": "126 W CHURCH ST",
                    "addr2": "SUITE 200",
                    "city": "DILLSBURG",
                    "zip": "170191280",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }],
            "physicians": [{
                "id": "row_7742",
                "count": 1999,
                "entity": {
                    "specialty": "DIAGNOSTIC RADIOLOGY",
                    "npi": 1124012851,
                    "school": "ALBANY MEDICAL COLLEGE OF UNION UNIVERSITY",
                    "first": "STEVEN",
                    "degree": "MD",
                    "last": "GILMAN"
                }
            }],
            "businesses": [{
                "id": "row_90125",
                "count": 225,
                "entity": {
                    "addr": "20 CAPITAL DR",
                    "addr2": "",
                    "city": "HARRISBURG",
                    "zip": "171109446",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": "row_90767",
                "count": 256,
                "entity": {
                    "addr": "4665 E TRINDLE RD",
                    "addr2": "",
                    "city": "MECHANICSBURG",
                    "zip": "170503640",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": "row_88742",
                "count": 246,
                "entity": {
                    "addr": "1211 FORGE RD",
                    "addr2": "",
                    "city": "CARLISLE",
                    "zip": "170133183",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": "row_90094",
                "count": 285,
                "entity": {
                    "addr": "2313 OAKFIELD RD",
                    "addr2": "",
                    "city": "ARLINGTON",
                    "zip": "189762010",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": "row_91720",
                "count": 251,
                "entity": {
                    "addr": "126 W CHURCH ST",
                    "addr2": "SUITE 200",
                    "city": "DILLSBURG",
                    "zip": "170191280",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": "row_88049",
                "count": 230,
                "entity": {
                    "addr": "431 N 21ST ST",
                    "addr2": "",
                    "city": "CAMP HILL",
                    "zip": "170112202",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": "row_86727",
                "count": 258,
                "entity": {
                    "addr": "429 N 21ST ST",
                    "addr2": "",
                    "city": "CAMP HILL",
                    "zip": "170112202",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }, {
                "id": "row_89758",
                "count": 249,
                "entity": {
                    "addr": "126 W CHURCH ST",
                    "addr2": "",
                    "city": "DILLSBURG",
                    "zip": "170191280",
                    "legal_name": "SPIRIT PHYSICIAN SERVICES INC"
                }
            }]
        }

    return pclean_row_response(
        pclean_resp=pclean_resp, 
        request=request, 
        english_query="dummy", 
        genfact_entity="dummy", 
        query_counter=query_counter)