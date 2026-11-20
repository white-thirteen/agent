import asyncio
from types import SimpleNamespace
from langchain_core.messages import HumanMessage, AIMessage
import app.context.compaction as c
from app.runtime.model_gateway import ModelGateway, ModelCallLimits, ModelCallContext, ModelCallUsage
from app.agents.types import AgentType
original=c.asummarize_messages
async def bad(*args, **kwargs):
    await original(*args, **kwargs)
    return SimpleNamespace(running_summary=None)
c.asummarize_messages=bad
class Model:
    def __init__(self, known): self.known=known; self.calls=0
    def bind(self,**kwargs): return self
    async def ainvoke(self,messages):
        self.calls+=1
        return AIMessage(content='summary',usage_metadata={'input_tokens':10,'output_tokens':2,'total_tokens':12} if self.known else None)
def counter(messages): return sum(len(str(m.content)) for m in messages)
async def main():
    for known in (True,False):
        m=Model(known)
        try:
            await c.summarize_messages([HumanMessage(content='test',id='1')],running_summary=None,gateway=ModelGateway(m,ModelCallLimits(8,3,0)),context=ModelCallContext('r','t',AgentType.SUPERVISOR),model_usage=ModelCallUsage(3),token_counter=counter,max_input_tokens=10000,max_output_tokens=100)
        except c.CompactionError as e:
            assert m.calls==1 and e.model_usage.model_attempts==4 and e.usage.status==('known' if known else 'unknown') and e.usage.total_tokens==(12 if known else None)
            print('known=',known,'calls=',m.calls,'attempts=',e.model_usage.model_attempts,'status=',e.usage.status,'total=',e.usage.total_tokens,'cause=',type(e.__cause__).__name__)
asyncio.run(main())
