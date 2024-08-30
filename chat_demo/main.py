from fastapi import FastAPI, Request, Form
from jinja2_fragments.fastapi import Jinja2Blocks
from typing import Annotated, Callable

import jinja2
import json
import logging as log
import requests
import traceback

from .chat_demo_server import ChatDemoServer


log.getLogger().setLevel(log.DEBUG)
log.getLogger("jax").setLevel(log.WARNING)
log.getLogger("asyncio").setLevel(log.WARNING)
log.getLogger("multipart.multipart").setLevel(log.WARNING)

templates = ChatDemoServer.get_templates("src")


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

default_context = {"page_title": "GenFact demo",
                   # "extra_js_scripts": "<script>console.log('foo')</script>",
                   # "extra_css": "<style>button {color: red !important}</style>",
                   "english_query_placeholder": "Provide a short sentence containing mentions of doctors",
                   "row_result_template": "row_result_genfact.html.jinja",
                   "query2_template": "query2_genfact.html.jinja"}


async def query1_callback(request: Request, english_query: str, query_counter):

    try:
        sample_response = json.loads('''
            {
                "posterior": {
                    "<style>\\n  .extracted_firstname { color: red; }\\n  .extracted_lastname { color: blue; }\\n  .extracted_specialty { color: green; }\\n  .extracted_legalname { color: orange; }\\n  .extracted_address { color: yellow; }\\n  .extracted_address2 { color: purple; }\\n  .extracted_c2z3 { color: violet; }</style><p><span class=\\"extracted_firstname\\">John</span> <span class=\\"extracted_lastname\\">Smith</span>'s <span class=\\"extracted_specialty\\">neurology</span> office (<span class=\\"extracted_legalname\\">Happy Brain Serviecs LLC</span> at <span class=\\"extracted_address\\">512 Example Street</span> <span class=\\"extracted_address2\\">Suite 3600</span> (<span class=\\"extracted_c2z3\\">CA-170</span>) is terrible!": {
                        "likelihood": 0.7,
                        "as_object": {
                            "first_name": "John",
                            "last_name": "Smith",
                            "specialty": "neurology",
                            "legal_name": "Happy Brain Services LLC",
                            "address": "512 Example Street",
                            "address2": "Suite 3600",
                            "c2z3": "CA-170"
                        }
                    },
                    "<style>\\n  .extracted_firstname { color: red; }\\n  .extracted_lastname { color: blue; }\\n  .extracted_specialty { color: green; }\\n  .extracted_legalname { color: orange; }\\n  .extracted_address { color: yellow; }\\n  .extracted_address2 { color: purple; }\\n  .extracted_c2z3 { color: violet; }</style><p><span class=\\"extracted_firstname\\">John</span> <span class=\\"extracted_lastname\\">Smith</span>'s <span class=\\"extracted_specialty\\">neurology</span> office (<span class=\\"extracted_legalname\\">Happy Brain Serviecs LLC</span> at <span class=\\"extracted_address\\">512 Example Street Suite 3600</span> (<span class=\\"extracted_c2z3\\">CA-170</span>) is terrible!": {
                        "likelihood": 0.3,
                        "as_object": {
                            "first_name": "John",
                            "last_name": "Smith",
                            "specialty": "neurology",
                            "legal_name": "Happy Brain Services LLC",
                            "address": "512 Example Street Suite 3600",
                            "address2": "",
                            "c2z3": "CA-170"
                        }
                    }
                }
            }
                                     ''')

        entities = [{'entity_html': k, 'pval': v['likelihood'], **v} for k, v in sample_response['posterior'].items()]
        for entity in entities:
            if 'as_object' in entity:
                entity['as_object'] = {k: v for k, v in entity['as_object'].items() if v != 'NONE'}
        entities.sort(key=lambda x: x['pval'], reverse=True)

        return templates.TemplateResponse(
            "index.html.jinja",
            default_context | 
            {"request": request, 
            "idnum": next(query_counter),
            "ml_entity": entities[0],
            "genfact_entities": entities},
            block_name="query2",
        )
        
    except Exception as e:
        import ipdb 
        ipdb.set_trace()

        log.error(f"Error in GenParse on English query (\"{english_query}\") : {e}")
        return templates.TemplateResponse(
            "index.html.jinja",
            default_context | 
            {"request": request, 
             "idnum": next(query_counter),
             "ml_entity": None,
             "genfact_entities": [],
             "error": f"{e}"
             },
            block_name="query2")
    

async def query2_callback(request: Request, query_counter, **kwargs):
    log.debug(f"Received kwargs: {kwargs}")
    return post_pclean_dummy(request, query_counter)


# Create and setup the server
server = ChatDemoServer(templates, default_context, query1_callback, query2_callback)
server.setup_routes() # Create the default routes
app = server.get_app() # Expose the app for uvicorn CLI


def pclean_row_response(*, pclean_resp: dict, request, english_query, genfact_entity, entity_html, query_counter, query2_modified):
    log.debug(f"pclean response: {pclean_resp}")

    docs, biz, doc_keys, biz_keys = extract_docs_and_biz(pclean_resp).values()
    
    # Add any extra fields to the end of the standard list
    doc_keys = physician_fields + list(doc_keys - set(physician_fields))
    biz_keys = business_fields + list(biz_keys - set(business_fields))
    
    joint, joint_keys = extract_joint(pclean_resp).values()
    joint_keys = joint_fields + list(joint_keys - set(joint_fields))

    return templates.TemplateResponse(
        "index.html.jinja",
        default_context | 
        {"request": request, 
        "idnum": next(query_counter),
        "physician_fields": physician_fields,
        "business_fields": business_fields,
        "joint_fields": joint_fields,
        "english_query": english_query,
        "genfact_entity": genfact_entity,
        "query2_html": entity_html,
        "docs": docs,
        "biz": biz,
        "joint": joint,
        "doc_keys": doc_keys,
        "biz_keys": biz_keys,
        "joint_keys": joint_keys,
        "query2_modified": query2_modified
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
        entity_html="<span style='color: red'>dummy</span>",
        query_counter=query_counter,
        query2_modified='0')