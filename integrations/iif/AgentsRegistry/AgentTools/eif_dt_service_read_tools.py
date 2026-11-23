"""IIF_DT registrations for the fixed PMem service read functions."""
from llama_index.core.tools import FunctionTool
from AgentsRegistry.CodedTools.eif_dt_service_reads import (
    eif_dt_list_catalog_products, eif_dt_read_catalog_product, eif_dt_read_ceim_contract,
)

catalog_products_tool = FunctionTool.from_defaults(fn=eif_dt_list_catalog_products)
catalog_product_tool = FunctionTool.from_defaults(fn=eif_dt_read_catalog_product)
ceim_contract_tool = FunctionTool.from_defaults(fn=eif_dt_read_ceim_contract)
