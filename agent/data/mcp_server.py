"""Local, read-only MCP. Run: python -m agent.data.mcp_server"""
from contextlib import asynccontextmanager
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from agent.data.data_access import PetDataAccess
from agent.data.tools.pet_data import make_pet_queries
from backend.app.config.container import build_container
from backend.app.config.settings import get_settings

_container=None
class LazyPets:
    def __getattr__(self,name):
        if _container is None:
            raise RuntimeError('Pet data server has not started')
        return getattr(_container.pets,name)

@asynccontextmanager
async def lifespan(_):
    global _container
    _container=await build_container(get_settings())
    try:
        yield
    finally:
        await _container.aclose()
        _container=None

server=MCPServer('hk-pet-data', lifespan=lifespan,instructions='Read-only HK pet data. Discover filters with get_pet_catalog. No payments, bookings, arbitrary browsing or availability guesses.')
for query in make_pet_queries(PetDataAccess(LazyPets())):
    server.tool(annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=query.__name__!='search_pet_places',openWorldHint=True))(query)
if __name__=='__main__':
    server.run(transport='stdio')
