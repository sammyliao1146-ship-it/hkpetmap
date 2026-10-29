from backend.app.observability.trace import TraceHooks
from contextlib import AsyncExitStack
from pathlib import Path
import sys
import json
from agents import Agent, ModelSettings, OpenAIResponsesModel, RunConfig, Runner
from agents.mcp import MCPServerStdio
from openai.types.shared import Reasoning
from agent.assembly.client_pool import get_client
from agent.data.data_access import PetDataAccess
from agent.subagents.intent_router import IntentDecision, main_agent_directive
from agent.assembly.prompts import instructions_for_language
from agent.data.tools.pet_data import make_pet_tools

async def run_pet_assistant(message: str, *, api_key: str, base_url: str, model: str, access: PetDataAccess,
                            tool_transport: str='function', language: str='zh-Hant', history: list[dict[str,str]] | None=None, intent: IntentDecision | None=None, web_knowledge=None,
                            reasoning_effort: str='', on_delta=None) -> str:
    origin_directive=(f'\nThe user explicitly shared origin latitude={access.origin[0]}, longitude={access.origin[1]} for this request. Use these exact coordinates in distance/radius tool calls, including MCP calls. They are not a verified route.' if access.origin else '')
    if tool_transport not in {'function','mcp_stdio'}:
        raise ValueError('Unsupported tool transport')
    client=get_client(api_key,base_url,40)
    async with AsyncExitStack() as stack:
        servers=[]
        if tool_transport=='mcp_stdio':
            server=MCPServerStdio(params={'command':sys.executable,'args':['-m','agent.data.mcp_server'],
                'cwd':str(Path(__file__).resolve().parents[2]),'env':{}},name='hk-pet-data',cache_tools_list=True,client_session_timeout_seconds=90)
            servers.append(await stack.enter_async_context(server))
        web_tools=[web_knowledge.tool(language,history=history)] if web_knowledge is not None else []
        assistant=Agent(name='香港毛孩助手',instructions=instructions_for_language(language)+origin_directive+(('\n\n'+main_agent_directive(intent)) if intent else ''),
            model=OpenAIResponsesModel(model=model,openai_client=client),
            model_settings=ModelSettings(reasoning=Reasoning(effort=reasoning_effort)) if reasoning_effort else ModelSettings(),
            tools=([t for t in make_pet_tools(access) if t.name!='get_pet_catalog'] if tool_transport=='function' else [])+web_tools,mcp_servers=servers)
        context={'catalogue':await access.catalog(),'recent_places':access.recent_places(history)}
        recent_history=[{**m,'content':m['content'] if m.get('role')=='user' else m['content'][:2400]} for m in (history or [])[-6:]]
        messages=[*recent_history,{'role':'user','content':json.dumps({'question':message,'map_context':context},ensure_ascii=False)}]
        if on_delta is None:
            result=await Runner.run(assistant,messages,max_turns=8,hooks=TraceHooks("main_agent", model),run_config=RunConfig(tracing_disabled=True))
        else:
            result=Runner.run_streamed(assistant,messages,max_turns=8,hooks=TraceHooks("main_agent", model),run_config=RunConfig(tracing_disabled=True))
            async for event in result.stream_events():
                if event.type=='raw_response_event' and event.data.type=='response.output_text.delta':
                    await on_delta(event.data.delta)
        return str(result.final_output)
