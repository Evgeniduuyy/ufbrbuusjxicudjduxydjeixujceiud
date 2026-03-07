from bs4 import BeautifulSoup

class TasksFetcher:
    def __init__(self, auth):
        self.auth = auth

    async def fetch_tasks(self) -> list:
        session = await self.auth.get_session()
        url = "https://school.mos.ru/api/homeworks"
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            tasks = []
            for item in data.get('homeworks', []):
                tasks.append({
                    'id': item['id'],
                    'subject': item['subject'],
                    'title': item['title'],
                    'deadline': item['deadline'],
                    'status': item['status'],
                    'url': item.get('url', '')
                })
            return tasks
