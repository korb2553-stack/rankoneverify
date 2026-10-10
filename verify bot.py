import os

import discord
from discord.ext import commands

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())


@bot.event
async def setup_hook():
    await bot.load_extension("verify")
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


bot.run(TOKEN)
