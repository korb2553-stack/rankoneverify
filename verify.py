import html
import json
import os
import urllib.parse

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands

CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REDIRECT_URI = os.environ["REDIRECT_URI"]  # เช่น https://โดเมนของคุณ/callback
GUILD_ID = int(os.environ["GUILD_ID"])
PORT = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or 8080)
CONFIG_PATH = "verify_config.json"
SITE_URL = REDIRECT_URI.rsplit("/callback", 1)[0]

DEFAULTS = {
    # ข้อความในห้อง
    "title": "ยืนยันตัวผ่านเว็บไซต์",
    "description": "➡️ คลิกปุ่มด้านล่างเพื่อเริ่มการยืนยันตัวตนและเข้าสู่เซิร์ฟเวอร์ครับ ❗",
    "button_label": "✅ ยืนยันตัวตน",
    "image_url": "",
    "color": "5865F2",
    # ยศ
    "role_ids": [],         # ยศที่ให้อัตโนมัติ
    "remove_role_ids": [],  # ยศที่ถอดออก (เช่น ยศรอยืนยัน)
    # หน้าเว็บ
    "ok_title": "ยืนยันตัวตนสำเร็จ",
    "ok_text": "กลับเข้า Discord เพื่อดูห้องต่างๆ ได้เลยครับ ✅",
    "err_title": "ทำรายการไม่สำเร็จ",
    "err_text": "คุณยกเลิกการเข้าสู่ระบบ หรือไม่ได้กดอนุญาตสิทธิ์บน Discord",
    "info_title": "ยืนยันตัวตนไปแล้ว",
    "info_text": "คุณยืนยันตัวตนไปแล้ว ไม่ต้องทำซ้ำนะครับ",
    "web_image_url": "",
    "why_button_label": "❗ ทำไมต้องยืนยันตัวตน?",
    "why_title": "ทำไมต้องยืนยันตัวตน?",
    "why_text": "เพื่อป้องกันบอทและบัญชีปลอมเข้ามาป่วนในเซิร์ฟเวอร์\nเราเข้าถึงแค่ชื่อผู้ใช้ รูปโปรไฟล์ และแบนเนอร์ของคุณเท่านั้น\nไม่สามารถอ่านข้อความหรือส่งข้อความแทนคุณได้",
    # ข้อความปุ่มที่โพสต์ไว้ [channel_id, message_id]
    "panel": None,
}

STYLES = {
    "ok": ("#3ba55d", "✓"),
    "err": ("#e05050", "✕"),
    "info": ("#e3b341", "i"),
    "brand": ("#5865F2", "?"),
}


def load_cfg() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return cfg


def save_cfg(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def page(cfg: dict, kind: str, title: str, text: str, buttons=()) -> web.Response:
    c, icon = STYLES[kind]
    btns = "".join(
        f'<a class="btn{" ghost" if g else ""}" href="{html.escape(u, quote=True)}">{html.escape(l)}</a>'
        for l, u, g in buttons)
    img = ""
    if cfg["web_image_url"].startswith(("http://", "https://")):
        img = f'<img src="{html.escape(cfg["web_image_url"], quote=True)}" style="max-width:100%;border-radius:16px;margin-bottom:20px">'
    body = f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#1e1f22;
font-family:system-ui,sans-serif;color:#fff}}
.card{{background:#2b2d31;border-radius:24px;padding:40px 28px;width:min(90vw,420px);
text-align:center;box-shadow:0 0 90px {c}40}}
.ic{{width:84px;height:84px;border-radius:50%;border:5px solid {c};color:{c};
font-size:44px;line-height:74px;margin:0 auto 24px;font-weight:700}}
h1{{color:{c};margin:0 0 12px;font-size:26px}}p{{color:#b5bac1;margin:0;line-height:1.7;white-space:pre-line}}
.btn{{display:block;margin-top:24px;padding:14px;border-radius:12px;background:{c};color:#fff;text-decoration:none;font-weight:700}}
.btn.ghost{{margin-top:12px;background:#383a40}}
</style></head><body><div class="card">{img}<div class="ic">{icon}</div>
<h1>{html.escape(title)}</h1><p>{html.escape(text)}</p>{btns}</div></body></html>"""
    return web.Response(text=body, content_type="text/html")


def auth_url() -> str:
    q = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
    })
    return "https://discord.com/oauth2/authorize?" + q


def build_panel(cfg: dict):
    try:
        color = int(cfg["color"].lstrip("#"), 16)
    except ValueError:
        color = 0x5865F2
    embed = discord.Embed(title=cfg["title"], description=cfg["description"], color=color)
    if cfg["image_url"].startswith(("http://", "https://")):
        embed.set_image(url=cfg["image_url"])
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label=cfg["button_label"], url=auth_url()))
    view.add_item(discord.ui.Button(label=cfg["why_button_label"], url=SITE_URL + "/why"))
    return embed, view


def roles_text(guild: discord.Guild, ids: list) -> str:
    out = [guild.get_role(i).mention for i in ids if guild.get_role(i)]
    return ", ".join(out) if out else "ไม่มี"


# ---------- หน้าต่างแก้ไข ----------
class TextModal(discord.ui.Modal, title="แก้ข้อความ/รูป/สี ในห้อง"):
    def __init__(self, cog: "Verify"):
        super().__init__()
        self.cog = cog
        c = cog.cfg
        self.t = discord.ui.TextInput(label="หัวข้อ", default=c["title"], max_length=256)
        self.d = discord.ui.TextInput(label="ข้อความ", default=c["description"],
                                      style=discord.TextStyle.paragraph, max_length=2000)
        self.b = discord.ui.TextInput(label="ข้อความบนปุ่ม", default=c["button_label"], max_length=80)
        self.i = discord.ui.TextInput(label="ลิงก์รูป (เว้นว่าง = ไม่มีรูป)", default=c["image_url"],
                                      required=False, max_length=500)
        self.c = discord.ui.TextInput(label="สี hex เช่น 5865F2", default=c["color"], max_length=7)
        for x in (self.t, self.d, self.b, self.i, self.c):
            self.add_item(x)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = self.cog.cfg
        cfg.update(title=self.t.value, description=self.d.value, button_label=self.b.value,
                   image_url=self.i.value.strip(), color=self.c.value.strip())
        save_cfg(cfg)
        await self.cog.refresh_panel()
        await interaction.response.send_message("บันทึกแล้ว (ข้อความที่โพสต์ไว้อัปเดตให้อัตโนมัติ)", ephemeral=True)


class WebModal(discord.ui.Modal, title="แก้ข้อความหน้าเว็บ"):
    def __init__(self, cog: "Verify"):
        super().__init__()
        self.cog = cog
        c = cog.cfg
        self.a = discord.ui.TextInput(label="หัวข้อเมื่อสำเร็จ (สีเขียว)", default=c["ok_title"], max_length=100)
        self.b = discord.ui.TextInput(label="ข้อความเมื่อสำเร็จ", default=c["ok_text"],
                                      style=discord.TextStyle.paragraph, max_length=300)
        self.c = discord.ui.TextInput(label="ข้อความเมื่อไม่สำเร็จ (สีแดง)", default=c["err_text"],
                                      style=discord.TextStyle.paragraph, max_length=300)
        self.d = discord.ui.TextInput(label="ข้อความเมื่อยืนยันไปแล้ว (สีเหลือง)", default=c["info_text"],
                                      style=discord.TextStyle.paragraph, max_length=300)
        self.e = discord.ui.TextInput(label="ลิงก์รูปบนหน้าเว็บ (เว้นว่างได้)", default=c["web_image_url"],
                                      required=False, max_length=500)
        for x in (self.a, self.b, self.c, self.d, self.e):
            self.add_item(x)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = self.cog.cfg
        cfg.update(ok_title=self.a.value, ok_text=self.b.value, err_text=self.c.value,
                   info_text=self.d.value, web_image_url=self.e.value.strip())
        save_cfg(cfg)
        await interaction.response.send_message("บันทึกแล้ว", ephemeral=True)


class WhyModal(discord.ui.Modal, title="แก้หน้า ทำไมต้องยืนยันตัวตน?"):
    def __init__(self, cog: "Verify"):
        super().__init__()
        self.cog = cog
        c = cog.cfg
        self.a = discord.ui.TextInput(label="ข้อความบนปุ่มที่สอง", default=c["why_button_label"], max_length=80)
        self.b = discord.ui.TextInput(label="หัวข้อหน้าเว็บ", default=c["why_title"], max_length=100)
        self.c = discord.ui.TextInput(label="เนื้อหา", default=c["why_text"],
                                      style=discord.TextStyle.paragraph, max_length=1500)
        for x in (self.a, self.b, self.c):
            self.add_item(x)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = self.cog.cfg
        cfg.update(why_button_label=self.a.value, why_title=self.b.value, why_text=self.c.value)
        save_cfg(cfg)
        await self.cog.refresh_panel()
        await interaction.response.send_message("บันทึกแล้ว", ephemeral=True)


class PanelView(discord.ui.View):
    def __init__(self, cog: "Verify", owner_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="✏️ ข้อความ/รูป/สี", style=discord.ButtonStyle.primary)
    async def edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextModal(self.cog))

    @discord.ui.button(label="🌐 หน้าเว็บ", style=discord.ButtonStyle.primary)
    async def edit_web(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WebModal(self.cog))

    @discord.ui.button(label="❓ หน้าทำไมต้องยืนยัน", style=discord.ButtonStyle.primary)
    async def edit_why(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WhyModal(self.cog))

    @discord.ui.button(label="📌 โพสต์ในห้องนี้", style=discord.ButtonStyle.success)
    async def post(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.post_panel(interaction.channel)
        await interaction.response.send_message("โพสต์แล้ว", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🎖️ ยศที่ให้อัตโนมัติ",
                       min_values=0, max_values=25, row=1)
    async def give_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await self._set_roles(interaction, "role_ids", select.values)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="➖ ยศที่ถอดออก (ไม่บังคับ)",
                       min_values=0, max_values=25, row=2)
    async def remove_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await self._set_roles(interaction, "remove_role_ids", select.values)

    async def _set_roles(self, interaction, key, roles):
        self.cog.cfg[key] = [r.id for r in roles]
        save_cfg(self.cog.cfg)
        top = interaction.guild.me.top_role
        bad = [r.mention for r in roles if r >= top or r.managed]
        msg = "บันทึกแล้ว: " + (", ".join(r.mention for r in roles) or "ไม่มี")
        if bad:
            msg += "\n⚠️ บอทให้ยศเหล่านี้ไม่ได้ (สูงกว่ายศบอท/เป็นยศระบบ): " + ", ".join(bad)
        await interaction.response.send_message(msg, ephemeral=True)


# ---------- Cog ----------
class Verify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = load_cfg()
        self.runner = None

    async def cog_load(self):
        app = web.Application()
        app.add_routes([web.get("/", self.index), web.get("/why", self.why),
                        web.get("/callback", self.callback)])
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, "0.0.0.0", PORT).start()

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()

    async def post_panel(self, channel: discord.abc.Messageable):
        await self._delete_old_panel()
        embed, view = build_panel(self.cfg)
        msg = await channel.send(embed=embed, view=view)
        self.cfg["panel"] = [msg.channel.id, msg.id]
        save_cfg(self.cfg)

    async def _delete_old_panel(self):
        if not self.cfg["panel"]:
            return
        try:
            ch = self.bot.get_channel(self.cfg["panel"][0]) or await self.bot.fetch_channel(self.cfg["panel"][0])
            await (await ch.fetch_message(self.cfg["panel"][1])).delete()
        except discord.HTTPException:
            pass

    async def refresh_panel(self):
        if not self.cfg["panel"]:
            return
        try:
            ch = self.bot.get_channel(self.cfg["panel"][0]) or await self.bot.fetch_channel(self.cfg["panel"][0])
            msg = await ch.fetch_message(self.cfg["panel"][1])
            embed, view = build_panel(self.cfg)
            await msg.edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

    async def index(self, request: web.Request) -> web.Response:
        c = self.cfg
        return page(c, "brand", c["title"], c["description"],
                    [("ยืนยันตัวตน", auth_url(), False), (c["why_title"], SITE_URL + "/why", True)])

    async def why(self, request: web.Request) -> web.Response:
        c = self.cfg
        return page(c, "brand", c["why_title"], c["why_text"],
                    [("ไปยืนยันตัวตน", auth_url(), False)])

    async def callback(self, request: web.Request) -> web.Response:
        cfg = self.cfg
        fail = page(cfg, "err", cfg["err_title"], cfg["err_text"])
        code = request.query.get("code")
        if request.query.get("error") or not code:
            return fail

        async with aiohttp.ClientSession() as s:
            async with s.post("https://discord.com/api/oauth2/token", data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            }) as r:
                if r.status != 200:
                    return fail
                token = (await r.json())["access_token"]
            async with s.get("https://discord.com/api/users/@me",
                             headers={"Authorization": f"Bearer {token}"}) as r:
                if r.status != 200:
                    return fail
                user = await r.json()

        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            return page(cfg, "err", "ระบบขัดข้อง", "ไม่พบเซิร์ฟเวอร์ กรุณาแจ้งแอดมินครับ")
        give = [guild.get_role(i) for i in cfg["role_ids"]]
        give = [r for r in give if r]
        if not give:
            return page(cfg, "err", "ระบบขัดข้อง", "แอดมินยังไม่ได้ตั้งยศที่จะให้ครับ")

        try:
            uid = int(user["id"])
            member = guild.get_member(uid) or await guild.fetch_member(uid)
        except discord.NotFound:
            return page(cfg, "err", "ไม่พบคุณในเซิร์ฟเวอร์",
                        "กรุณาเข้าเซิร์ฟเวอร์ก่อน แล้วกดยืนยันใหม่อีกครั้งครับ")

        if all(r in member.roles for r in give):
            return page(cfg, "info", cfg["info_title"], cfg["info_text"])

        remove = [guild.get_role(i) for i in cfg["remove_role_ids"]]
        remove = [r for r in remove if r and r in member.roles]
        try:
            await member.add_roles(*give, reason="Web verification")
            if remove:
                await member.remove_roles(*remove, reason="Web verification")
        except discord.Forbidden:
            return page(cfg, "err", "ระบบขัดข้อง", "บอทไม่มีสิทธิ์ให้ยศ กรุณาแจ้งแอดมินครับ")

        return page(cfg, "ok", cfg["ok_title"], cfg["ok_text"])

    @app_commands.command(name="verify_panel", description="ตั้งค่าระบบยืนยันตัวตน")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_panel(self, interaction: discord.Interaction):
        c = self.cfg
        g = interaction.guild
        await interaction.response.send_message(
            "**ตั้งค่าระบบยืนยันตัวตน**\n"
            f"🎖️ ยศที่ให้: {roles_text(g, c['role_ids'])}\n"
            f"➖ ยศที่ถอด: {roles_text(g, c['remove_role_ids'])}",
            view=PanelView(self, interaction.user.id), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verify(bot))
