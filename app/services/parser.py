import re
from bs4 import BeautifulSoup

class TaskParser:
    def __init__(self, auth):
        self.auth = auth

    async def parse(self, url: str) -> dict:
        session = await self.auth.get_session()
        async with session.get(url) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, 'lxml')
        question = soup.find('div', class_=re.compile(r'question-text|task-question'))
        question = question.get_text(strip=True) if question else ''
        options = []
        for opt in soup.find_all('label', class_=re.compile(r'answer-option|option-label')):
            text = opt.get_text(strip=True)
            inp = opt.find('input')
            opt_type = inp.get('type') if inp else None
            options.append({'text': text, 'type': opt_type})
        task_type = 'single_choice' if any(o['type']=='radio' for o in options) else \
                    'multiple_choice' if any(o['type']=='checkbox' for o in options) else \
                    'input' if options else 'unknown'
        attempts_text = soup.find(text=re.compile(r'Попытка\s+\d+\s+из\s+\d+', re.IGNORECASE))
        attempts_left = None
        if attempts_text:
            match = re.search(r'(\d+)\s+из\s+(\d+)', attempts_text)
            if match:
                current, total = int(match.group(1)), int(match.group(2))
                attempts_left = total - current + 1
        return {
            'url': url,
            'question': question,
            'options': options,
            'task_type': task_type,
            'attempts_left': attempts_left
        }
