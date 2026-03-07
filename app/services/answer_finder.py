import hashlib
import json
import openai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.answer import Answer
from app.config import Config

openai.api_key = Config.OPENAI_API_KEY

class AnswerFinder:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def find(self, task_data: dict) -> dict:
        url_hash = hashlib.sha256(task_data['url'].encode()).hexdigest()
        q_hash = hashlib.sha256(task_data.get('question','').encode()).hexdigest()
        stmt = select(Answer).where(Answer.task_url_hash==url_hash, Answer.question_hash==q_hash)
        ans = (await self.db.execute(stmt)).scalar_one_or_none()
        if ans:
            return json.loads(ans.answer_json)
        # AI fallback
        prompt = f"Реши задачу: {task_data['question']}\n"
        if task_data['options']:
            prompt += "Варианты:\n" + "\n".join(o['text'] for o in task_data['options'])
        try:
            resp = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            answer = resp.choices[0].message.content.strip()
            result = {"text": answer, "type": task_data['task_type']}
            new = Answer(
                task_url_hash=url_hash,
                question_hash=q_hash,
                question_text=task_data['question'],
                answer_json=json.dumps(result),
                source='ai'
            )
            self.db.add(new)
            await self.db.commit()
            return result
        except Exception:
            return None
