import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
INTENTS = discord.Intents.default()
INTENTS.message_content = True  # Required for reading message content
INTENTS.members = True  # Required for member info - MUST BE ENABLED IN DEVELOPER PORTAL
INTENTS.voice_states = True  # Required for voice tracking
INTENTS.guilds = True
INTENTS.reactions = True

bot = commands.Bot(command_prefix='!', intents=INTENTS)

# XP Configuration
XP_PER_MESSAGE = 10
XP_PER_REACTION = 5
XP_PER_MINUTE_VC = 2
MESSAGE_COOLDOWN = 60  # Seconds between XP gains from messages

# Database file
DB_FILE = 'xp_data.json'

# In-memory tracking
voice_join_times = {}  # Track when users join voice channels
message_cooldowns = {}  # Track message cooldowns per user


def load_data():
    """Load XP data from JSON file"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_data(data):
    """Save XP data to JSON file"""
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def get_user_data(data, guild_id, user_id, username=None):
    """Get user data, creating if doesn't exist"""
    guild_id = str(guild_id)
    user_id = str(user_id)

    if guild_id not in data:
        data[guild_id] = {}

    if user_id not in data[guild_id]:
        data[guild_id][user_id] = {
            'username': username or 'Unknown',
            'xp': 0,
            'level': 1,
            'messages': 0,
            'reactions': 0,
            'vc_minutes': 0
        }
    else:
        # Update username if provided (in case user changed their name)
        if username:
            data[guild_id][user_id]['username'] = username

    return data[guild_id][user_id]


def calculate_level(xp):
    """Calculate level based on XP (simple formula: level = sqrt(xp/100))"""
    import math
    return int(math.sqrt(xp / 100)) + 1


def xp_for_next_level(level):
    """Calculate XP needed for next level"""
    return (level ** 2) * 100


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')

    # Initialize voice_join_times for users already in voice channels
    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            for member in voice_channel.members:
                if not member.bot:
                    user_key = f"{guild.id}_{member.id}"
                    voice_join_times[user_key] = datetime.now()

    check_voice_xp.start()


@bot.event
async def on_message(message):
    """Award XP for messages"""
    # Ignore bot messages
    if message.author.bot:
        await bot.process_commands(message)
        return

    # Check cooldown
    user_key = f"{message.guild.id}_{message.author.id}"
    current_time = datetime.now()

    if user_key in message_cooldowns:
        if current_time - message_cooldowns[user_key] < timedelta(seconds=MESSAGE_COOLDOWN):
            await bot.process_commands(message)
            return

    # Update cooldown
    message_cooldowns[user_key] = current_time

    # Load data and award XP
    data = load_data()
    user_data = get_user_data(data, message.guild.id, message.author.id, str(message.author))

    old_level = user_data['level']
    user_data['xp'] += XP_PER_MESSAGE
    user_data['messages'] += 1
    user_data['level'] = calculate_level(user_data['xp'])

    save_data(data)

    # Check for level up
    if user_data['level'] > old_level:
        await message.channel.send(
            f"🎉 {message.author.mention} leveled up to **Level {user_data['level']}**!"
        )

    await bot.process_commands(message)


@bot.event
async def on_reaction_add(reaction, user):
    """Award XP for adding reactions"""
    # Ignore bot reactions
    if user.bot:
        return

    # Load data and award XP
    data = load_data()
    user_data = get_user_data(data, reaction.message.guild.id, user.id, str(user))

    old_level = user_data['level']
    user_data['xp'] += XP_PER_REACTION
    user_data['reactions'] += 1
    user_data['level'] = calculate_level(user_data['xp'])

    save_data(data)

    # Check for level up
    if user_data['level'] > old_level:
        await reaction.message.channel.send(
            f"🎉 {user.mention} leveled up to **Level {user_data['level']}**!"
        )


@bot.event
async def on_voice_state_update(member, before, after):
    """Track voice channel join/leave times"""
    # User joined a voice channel
    if before.channel is None and after.channel is not None:
        voice_join_times[f"{member.guild.id}_{member.id}"] = datetime.now()

    # User left a voice channel
    elif before.channel is not None and after.channel is None:
        user_key = f"{member.guild.id}_{member.id}"
        if user_key in voice_join_times:
            # Calculate time spent
            time_spent = datetime.now() - voice_join_times[user_key]
            minutes = int(time_spent.total_seconds() / 60)

            if minutes > 0:
                # Award XP
                data = load_data()
                user_data = get_user_data(data, member.guild.id, member.id, str(member))

                old_level = user_data['level']
                xp_gained = minutes * XP_PER_MINUTE_VC
                user_data['xp'] += xp_gained
                user_data['vc_minutes'] += minutes
                user_data['level'] = calculate_level(user_data['xp'])

                save_data(data)

                # Check for level up
                if user_data['level'] > old_level:
                    # Try to send message in a general channel
                    for channel in member.guild.text_channels:
                        if channel.permissions_for(member.guild.me).send_messages:
                            await channel.send(
                                f"🎉 {member.mention} leveled up to **Level {user_data['level']}** after spending time in voice chat!"
                            )
                            break

            del voice_join_times[user_key]


@tasks.loop(minutes=1)
async def check_voice_xp():
    """Periodically award XP to users currently in voice channels"""
    data = load_data()
    current_time = datetime.now()

    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            for member in voice_channel.members:
                if member.bot:
                    continue

                user_key = f"{guild.id}_{member.id}"
                if user_key in voice_join_times:
                    # Calculate actual time spent since last check
                    time_spent = current_time - voice_join_times[user_key]
                    minutes = int(time_spent.total_seconds() / 60)

                    if minutes > 0:
                        # Award XP for actual minutes spent
                        user_data = get_user_data(data, guild.id, member.id, str(member))
                        old_level = user_data['level']
                        xp_gained = minutes * XP_PER_MINUTE_VC
                        user_data['xp'] += xp_gained
                        user_data['vc_minutes'] += minutes
                        user_data['level'] = calculate_level(user_data['xp'])

                        # Check for level up
                        if user_data['level'] > old_level:
                            # Try to send message in a general channel
                            for channel in guild.text_channels:
                                if channel.permissions_for(guild.me).send_messages:
                                    await channel.send(
                                        f"🎉 {member.mention} leveled up to **Level {user_data['level']}** while in voice chat!"
                                    )
                                    break

                    # Reset the join time to now for next check
                    voice_join_times[user_key] = current_time

    save_data(data)


@bot.command(name='rank')
async def rank(ctx, member: discord.Member = None):
    """Check your or someone else's rank"""
    member = member or ctx.author

    data = load_data()
    user_data = get_user_data(data, ctx.guild.id, member.id)

    # Calculate rank
    guild_data = data.get(str(ctx.guild.id), {})
    sorted_users = sorted(guild_data.items(), key=lambda x: x[1]['xp'], reverse=True)
    rank = next((i + 1 for i, (uid, _) in enumerate(sorted_users) if uid == str(member.id)), 0)

    # Calculate XP for next level
    next_level_xp = xp_for_next_level(user_data['level'])
    xp_progress = user_data['xp'] - xp_for_next_level(user_data['level'] - 1)
    xp_needed = next_level_xp - xp_for_next_level(user_data['level'] - 1)

    embed = discord.Embed(title=f"📊 {member.display_name}'s Stats", color=discord.Color.blue())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Rank", value=f"#{rank}", inline=True)
    embed.add_field(name="Level", value=user_data['level'], inline=True)
    embed.add_field(name="Total XP", value=f"{user_data['xp']:,}", inline=True)
    embed.add_field(name="Progress", value=f"{xp_progress}/{xp_needed} XP to Level {user_data['level'] + 1}",
                    inline=False)
    embed.add_field(name="Messages", value=user_data['messages'], inline=True)
    embed.add_field(name="Reactions", value=user_data['reactions'], inline=True)
    embed.add_field(name="VC Minutes", value=user_data['vc_minutes'], inline=True)

    await ctx.send(embed=embed)


@bot.command(name='leaderboard')
async def leaderboard(ctx, page: int = 1):
    """Show the server leaderboard"""
    data = load_data()
    guild_data = data.get(str(ctx.guild.id), {})

    if not guild_data:
        await ctx.send("No XP data available yet!")
        return

    # Sort by XP
    sorted_users = sorted(guild_data.items(), key=lambda x: x[1]['xp'], reverse=True)

    # Pagination
    per_page = 10
    total_pages = (len(sorted_users) + per_page - 1) // per_page
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    embed = discord.Embed(
        title=f"🏆 {ctx.guild.name} Leaderboard",
        description=f"Page {page}/{total_pages}",
        color=discord.Color.gold()
    )

    for i, (user_id, user_data) in enumerate(sorted_users[start_idx:end_idx], start=start_idx + 1):
        try:
            member = await ctx.guild.fetch_member(int(user_id))
            name = member.display_name
        except:
            name = f"User {user_id}"

        medal = ""
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "

        embed.add_field(
            name=f"{medal}#{i} {name}",
            value=f"Level {user_data['level']} • {user_data['xp']:,} XP",
            inline=False
        )

    await ctx.send(embed=embed)


@bot.command(name='xpconfig')
@commands.has_permissions(administrator=True)
async def xp_config(ctx):
    """Show current XP configuration (Admin only)"""
    embed = discord.Embed(title="⚙️ XP Configuration", color=discord.Color.green())
    embed.add_field(name="XP per Message", value=XP_PER_MESSAGE, inline=True)
    embed.add_field(name="XP per Reaction", value=XP_PER_REACTION, inline=True)
    embed.add_field(name="XP per VC Minute", value=XP_PER_MINUTE_VC, inline=True)
    embed.add_field(name="Message Cooldown", value=f"{MESSAGE_COOLDOWN}s", inline=True)

    await ctx.send(embed=embed)


@bot.command(name='resetxp')
@commands.has_permissions(administrator=True)
async def reset_xp(ctx, member: discord.Member):
    """Reset a user's XP (Admin only)"""
    data = load_data()
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)

    if guild_id in data and user_id in data[guild_id]:
        del data[guild_id][user_id]
        save_data(data)
        await ctx.send(f"✅ Reset XP for {member.display_name}")
    else:
        await ctx.send(f"❌ No XP data found for {member.display_name}")


if __name__ == '__main__':
    # Get token from environment variable or replace with your token
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')

    if not TOKEN:
        print("ERROR: Please set DISCORD_BOT_TOKEN environment variable")
        print("Or replace the TOKEN line with: TOKEN = 'your-bot-token-here'")
    else:
        bot.run(TOKEN)