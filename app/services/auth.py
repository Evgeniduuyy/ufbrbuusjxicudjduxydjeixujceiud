import aiohttp
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.session import UserSession
from app.utils.crypto import encrypt, decrypt

class MESAuth:
    LOGIN_URL = "https://login.mos.ru/sso/login"
    SCHOOL_URL = "https://school.mos.ru"

    def __init__(self, user_id: int, db_session: AsyncSession):
        self.user_id = user_id
        self.db = db_session
        self.session = None

    async def _load_session(self):
        stmt = select(UserSession).where(UserSession.user_id == self.user_id)
        result = await self.db.execute(stmt)
        sess = result.scalar_one_or_none()
        if sess and sess.cookies_json:
            cookies = json.loads(decrypt(sess.cookies_json))
            connector = aiohttp.TCPConnector(ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)
            for name, value in cookies.items():
                self.session.cookie_jar.update_cookies({name: value})
            return True
        return False

    async def login(self, login: str, password: str, otp: str = None) -> bool:
        connector = aiohttp.TCPConnector(ssl=False)
        self.session = aiohttp.ClientSession(connector=connector)
        await self.session.get(self.SCHOOL_URL)
        data = {"login": login, "password": password}
        if otp:
            data["otp"] = otp
        async with self.session.post(self.LOGIN_URL, data=data) as resp:
            if resp.status != 200:
                return False
        jar = self.session.cookie_jar.filter_cookies(self.SCHOOL_URL)
        cookies = {k: v.value for k, v in jar.items()}
        encrypted = encrypt(json.dumps(cookies))
        stmt = select(UserSession).where(UserSession.user_id == self.user_id)
        result = await self.db.execute(stmt)
        sess = result.scalar_one_or_none()
        if sess:
            sess.cookies_json = encrypted
        else:
            sess = UserSession(
                user_id=self.user_id,
                encrypted_login=encrypt(login),
                encrypted_password=encrypt(password),
                cookies_json=encrypted
            )
            self.db.add(sess)
        await self.db.commit()
        return True

    async def get_session(self) -> aiohttp.ClientSession:
        if not self.session:
            if not await self._load_session():
                raise Exception("No active session")
        return self.session

    async def close(self):
        if self.session:
            await self.session.close()
