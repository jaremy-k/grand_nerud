from bson import ObjectId

from app.deals.shemas import SDealsInput, SDealsStageUpdate


def test_deal_input_accepts_string_object_ids():
    service_id = ObjectId()
    customer_id = ObjectId()
    provider_id = ObjectId()
    stage_id = ObjectId()
    material_id = ObjectId()

    deal = SDealsInput(
        serviceId=str(service_id),
        customerId=str(customer_id),
        providerId=str(provider_id),
        stageId=str(stage_id),
        materialId=str(material_id),
    )

    assert deal.serviceId == service_id
    assert deal.customerId == customer_id
    assert deal.providerId == provider_id
    assert deal.stageId == stage_id
    assert deal.materialId == material_id


def test_deal_stage_update_accepts_string_object_id():
    stage_id = ObjectId()

    value = SDealsStageUpdate(stageId=str(stage_id))

    assert value.stageId == stage_id
