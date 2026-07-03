import json
from datetime import date, datetime
from typing import Any, List

from bson import ObjectId


class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def serialize_mongo_doc(doc: dict) -> dict:
    return json.loads(json.dumps(doc, cls=MongoJSONEncoder, default=str))


def serialize_mongo_docs(docs: List[dict]) -> List[dict]:
    return [serialize_mongo_doc(doc) for doc in docs]


def convert_objectids_to_str(data: Any) -> Any:
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key == "unitMeasurement" and (value == "" or value is None):
                result[key] = None
            else:
                result[key] = convert_objectids_to_str(value)
        return result
    if isinstance(data, list):
        return [convert_objectids_to_str(item) for item in data]
    return data
