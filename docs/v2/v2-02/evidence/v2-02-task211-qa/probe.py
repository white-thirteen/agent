import asyncio
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.context.compaction import summarize_messages
from app.runtime.model_gateway import ModelGateway, ModelCallLimits, ModelCallUsage, ModelCallContext
from app.agents.types import AgentType

class Model:
    def __init__(self): self.calls = 0
    def bind(self, **kwargs): return self
    async def ainvoke(self, messages):
        self.calls += 1
        return AIMessage(content='summary', usage_metadata={'input_tokens':10,'output_tokens':2,'total_tokens':12})

def counter(messages): return sum(len(str(message.content)) for message in messages)

async def main():
    model = Model()
    kw = dict(gateway=ModelGateway(model, ModelCallLimits(8,3,0)), context=ModelCallContext('r','t',AgentType.SUPERVISOR), token_counter=counter, max_input_tokens=10000, max_output_tokens=100)
    a=HumanMessage(content='first',id='1'); b=HumanMessage(content='second',id='2')
    s,u,_=await summarize_messages([a],running_summary=None,model_usage=ModelCallUsage(),**kw)
    for label,messages in [('full',[a,b]),('new',[b]),('replay',[a])]:
        before=model.calls
        try:
            result,usage,reports=await summarize_messages(messages,running_summary=s,model_usage=u,**kw)
            print(label,sorted(result.summarized_message_ids),usage.model_attempts,'calls',model.calls-before)
        except Exception as exc: print(label,type(exc).__name__,str(exc),'calls',model.calls-before)
    before=model.calls
    try:
        await summarize_messages([SystemMessage(content='',id='s'),HumanMessage(content='hello',id='h')],running_summary=None,model_usage=ModelCallUsage(),**kw)
    except Exception as exc:
        print('post-call',type(exc).__name__,str(exc),'calls',model.calls-before,'model_usage',getattr(exc,'model_usage',None),'usage',getattr(exc,'usage',None))

asyncio.run(main())
