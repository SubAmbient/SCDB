import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Bot version
BOT_VERSION = "0.0.9"

# Load environment variables from .env file
load_dotenv()

# Get levelup channel ID from environment (optional)
LEVELUP_CHANNEL_ID = os.getenv('LEVELUP_CHANNEL_ID')
if LEVELUP_CHANNEL_ID:
    LEVELUP_CHANNEL_ID = int(LEVELUP_CHANNEL_ID)

# Bot configuration
INTENTS = discord.Intents.default()
INTENTS.message_content = True  # Required for reading message content
INTENTS.members = True  # Required for member info - MUST BE ENABLED IN DEVELOPER PORTAL
INTENTS.voice_states = True  # Required for voice tracking
INTENTS.guilds = True
INTENTS.reactions = True

bot = commands.Bot(command_prefix='!', intents=INTENTS, help_command=None)

# Configuration files
CONFIG_FILE = 'config.json'
DB_FILE = 'xp_data.json'

# Default XP Configuration
DEFAULT_CONFIG = {
    'xp_per_message': 5,
    'xp_per_reaction': 5,
    'xp_per_minute_vc': 2,
    'message_cooldown': 10
}


# Load or create config
def load_config():
    """Load configuration from JSON file, create if doesn't exist"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    else:
        # Create config file with defaults
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print(f"Created {CONFIG_FILE} with default values")
        return DEFAULT_CONFIG.copy()


# Load configuration
config = load_config()
XP_PER_MESSAGE = config.get('xp_per_message', DEFAULT_CONFIG['xp_per_message'])
XP_PER_REACTION = config.get('xp_per_reaction', DEFAULT_CONFIG['xp_per_reaction'])
XP_PER_MINUTE_VC = config.get('xp_per_minute_vc', DEFAULT_CONFIG['xp_per_minute_vc'])
MESSAGE_COOLDOWN = config.get('message_cooldown', DEFAULT_CONFIG['message_cooldown'])

# In-memory tracking
voice_join_times = {}  # Track when users join voice channels
voice_session_starts = {}  # Track session start time for longest session calculation
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
            'vc_seconds': 0,
            'vc_partners': {},  # Track time with each voice channel partner
            'longest_session': 0,  # Longest single VC session in seconds
            'longest_session_date': None  # When the longest session occurred
        }
    else:
        # Update username if provided (in case user changed their name)
        if username:
            data[guild_id][user_id]['username'] = username

        # Ensure vc_partners exists for existing users
        if 'vc_partners' not in data[guild_id][user_id]:
            data[guild_id][user_id]['vc_partners'] = {}

        # Ensure longest_session fields exist for existing users
        if 'longest_session' not in data[guild_id][user_id]:
            data[guild_id][user_id]['longest_session'] = 0
        if 'longest_session_date' not in data[guild_id][user_id]:
            data[guild_id][user_id]['longest_session_date'] = None

    return data[guild_id][user_id]


def calculate_level(xp):
    """Calculate level based on XP (simple formula: level = sqrt(xp/100))"""
    import math
    return int(math.sqrt(xp / 100)) + 1


def xp_for_next_level(level):
    """Calculate XP needed for next level"""
    return (level ** 2) * 100


def format_time(seconds):
    """Format seconds into human-readable time string"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


async def send_levelup_message(guild, member, level, context_channel=None):
    """Send level-up message to configured channel or fallback to context channel"""
    message = f"🎉 {member.mention} leveled up to **Level {level}**!"

    # Try to send to configured channel first
    if LEVELUP_CHANNEL_ID:
        channel = guild.get_channel(LEVELUP_CHANNEL_ID)
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(message)
            return

    # Fallback to context channel if provided
    if context_channel and context_channel.permissions_for(guild.me).send_messages:
        await context_channel.send(message)
        return

    # Last resort: find any channel we can send to
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(message)
            break


@bot.event
async def on_ready():
    print(f'Bot Version: {BOT_VERSION}')
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')

    if LEVELUP_CHANNEL_ID:
        print(f'Level-up messages will be sent to channel ID: {LEVELUP_CHANNEL_ID}')
    else:
        print('No level-up channel configured - messages will be sent in context channel')

    # Initialize voice_join_times for users already in voice channels
    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            for member in voice_channel.members:
                if not member.bot:
                    user_key = f"{guild.id}_{member.id}"
                    voice_join_times[user_key] = datetime.now()
                    voice_session_starts[user_key] = datetime.now()

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
        await send_levelup_message(message.guild, message.author, user_data['level'], message.channel)

    await bot.process_commands(message)


@bot.event
async def on_raw_reaction_add(payload):
    """Award XP for adding reactions and receiving reactions (works for all messages, not just cached)"""
    # Ignore bot reactions
    if payload.member and payload.member.bot:
        return

    # Get guild
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    # Get the channel
    channel = guild.get_channel(payload.channel_id)
    if not channel:
        return

    # Fetch the message
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return
    except discord.Forbidden:
        return
    except discord.HTTPException:
        return

    # Get the user who reacted
    user = payload.member

    # Load data
    data = load_data()

    # Award XP to the person who added the reaction
    user_data = get_user_data(data, guild.id, user.id, str(user))

    old_level = user_data['level']
    user_data['xp'] += XP_PER_REACTION
    user_data['reactions'] += 1
    user_data['level'] = calculate_level(user_data['xp'])

    # Check for level up for the person who reacted
    if user_data['level'] > old_level:
        await send_levelup_message(guild, user, user_data['level'], channel)

    # Award XP to the message author (if they're not a bot and not reacting to their own message)
    if not message.author.bot and message.author.id != user.id:
        author_data = get_user_data(data, guild.id, message.author.id, str(message.author))

        old_author_level = author_data['level']
        author_data['xp'] += XP_PER_REACTION
        author_data['level'] = calculate_level(author_data['xp'])

        # Check for level up for the message author
        if author_data['level'] > old_author_level:
            await send_levelup_message(guild, message.author, author_data['level'], channel)

    save_data(data)


@bot.event
async def on_voice_state_update(member, before, after):
    """Track voice channel join/leave times and record longest sessions"""
    if member.bot:
        return

    user_key = f"{member.guild.id}_{member.id}"

    # User joined a voice channel
    if before.channel is None and after.channel is not None:
        voice_join_times[user_key] = datetime.now()
        voice_session_starts[user_key] = datetime.now()

    # User left a voice channel
    elif before.channel is not None and after.channel is None:
        if user_key in voice_session_starts:
            # Calculate session duration
            session_duration = int((datetime.now() - voice_session_starts[user_key]).total_seconds())

            # Load data and update longest session if needed
            data = load_data()
            user_data = get_user_data(data, member.guild.id, member.id, str(member))

            # Check if this session is longer than the current record
            if session_duration > user_data['longest_session']:
                user_data['longest_session'] = session_duration
                user_data['longest_session_date'] = datetime.now().isoformat()
                save_data(data)

            # Clean up tracking
            del voice_session_starts[user_key]

        if user_key in voice_join_times:
            del voice_join_times[user_key]


@tasks.loop(minutes=1)
async def check_voice_xp():
    """Periodically award XP to users currently in voice channels and track partner time"""
    data = load_data()

    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            # Count non-bot, non-muted members in the channel
            non_bot_members = [m for m in voice_channel.members if
                               not m.bot and not m.voice.self_mute and not m.voice.mute]

            # Skip if only one person (or no one) is in the channel
            if len(non_bot_members) <= 1:
                continue

            for member in non_bot_members:
                user_key = f"{guild.id}_{member.id}"
                if user_key in voice_join_times:
                    # Award XP for 1 minute (60 seconds)
                    user_data = get_user_data(data, guild.id, member.id, str(member))
                    old_level = user_data['level']

                    user_data['xp'] += XP_PER_MINUTE_VC
                    user_data['vc_seconds'] += 60
                    user_data['level'] = calculate_level(user_data['xp'])

                    # Track time with each partner in the voice channel
                    for partner in non_bot_members:
                        if partner.id != member.id:  # Don't track time with yourself
                            partner_id = str(partner.id)
                            if partner_id not in user_data['vc_partners']:
                                user_data['vc_partners'][partner_id] = {
                                    'username': str(partner),
                                    'seconds': 0
                                }
                            user_data['vc_partners'][partner_id]['seconds'] += 60
                            user_data['vc_partners'][partner_id]['username'] = str(partner)  # Update username

                    # Check for level up
                    if user_data['level'] > old_level:
                        await send_levelup_message(guild, member, user_data['level'])

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

    # Format VC time
    vc_time_str = format_time(user_data.get('vc_seconds', 0))
    embed.add_field(name="VC Time", value=vc_time_str, inline=True)

    # Add longest session info
    longest_session = user_data.get('longest_session', 0)
    if longest_session > 0:
        longest_str = format_time(longest_session)
        embed.add_field(name="🏆 Longest Session", value=longest_str, inline=True)

    await ctx.send(embed=embed)


@bot.command(name='vcpartners')
async def vc_partners(ctx, member: discord.Member = None):
    """Show who you've spent the most time with in voice channels"""
    member = member or ctx.author

    data = load_data()
    user_data = get_user_data(data, ctx.guild.id, member.id)

    vc_partners = user_data.get('vc_partners', {})

    if not vc_partners:
        await ctx.send(f"{member.display_name} hasn't spent time in voice channels with anyone yet!")
        return

    # Sort partners by time spent
    sorted_partners = sorted(vc_partners.items(), key=lambda x: x[1]['seconds'], reverse=True)

    embed = discord.Embed(
        title=f"🎙️ {member.display_name}'s Voice Channel Partners",
        description=f"Top people {member.display_name} has spent time with in voice channels",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    # Show top 10 partners
    for i, (partner_id, partner_data) in enumerate(sorted_partners[:10], 1):
        time_str = format_time(partner_data['seconds'])

        # Try to get the actual member for display name
        try:
            partner_member = await ctx.guild.fetch_member(int(partner_id))
            partner_name = partner_member.display_name
        except:
            partner_name = partner_data.get('username', f'User {partner_id}')

        medal = ""
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "

        embed.add_field(
            name=f"{medal}#{i} {partner_name}",
            value=f"⏱️ {time_str}",
            inline=False
        )

    total_partners = len(vc_partners)
    if total_partners > 10:
        embed.set_footer(text=f"Showing top 10 of {total_partners} partners")

    await ctx.send(embed=embed)


@bot.command(name='leaderboard')
async def leaderboard(ctx, category: str = 'xp', page: int = 1):
    """Show the server leaderboard

    Categories: xp, level, messages, reactions, vc (voice chat time), session (longest session)
    Usage: !leaderboard [category] [page]
    Example: !leaderboard session 1
    """
    data = load_data()
    guild_data = data.get(str(ctx.guild.id), {})

    if not guild_data:
        await ctx.send("No XP data available yet!")
        return

    # Validate and normalize category
    category = category.lower()
    valid_categories = {
        'xp': ('xp', '🏆 XP', 'XP'),
        'level': ('level', '⭐ Level', 'Level'),
        'messages': ('messages', '💬 Messages', 'Messages'),
        'reactions': ('reactions', '❤️ Reactions', 'Reactions'),
        'vc': ('vc_seconds', '🎙️ Voice Time', 'Time'),
        'vctime': ('vc_seconds', '🎙️ Voice Time', 'Time'),
        'voice': ('vc_seconds', '🎙️ Voice Time', 'Time'),
        'session': ('longest_session', '⏱️ Longest Session', 'Session'),
        'longest': ('longest_session', '⏱️ Longest Session', 'Session')
    }

    if category not in valid_categories:
        await ctx.send(f"❌ Invalid category! Use: `xp`, `level`, `messages`, `reactions`, `vc`, or `session`")
        return

    sort_key, title_emoji, stat_name = valid_categories[category]

    # Sort by selected category
    sorted_users = sorted(guild_data.items(), key=lambda x: x[1].get(sort_key, 0), reverse=True)

    # Pagination
    per_page = 10
    total_pages = (len(sorted_users) + per_page - 1) // per_page
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    embed = discord.Embed(
        title=f"{title_emoji} Leaderboard - {ctx.guild.name}",
        description=f"Page {page}/{total_pages}",
        color=discord.Color.gold()
    )

    for i, (user_id, user_data) in enumerate(sorted_users[start_idx:end_idx], start=start_idx + 1):
        try:
            member = await ctx.guild.fetch_member(int(user_id))
            name = member.display_name
        except:
            name = user_data.get('username', f"User {user_id}")

        medal = ""
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "

        # Format the stat value based on category
        stat_value = user_data.get(sort_key, 0)

        if sort_key in ['vc_seconds', 'longest_session']:
            # Format time
            formatted_stat = format_time(stat_value)
            value_text = f"{formatted_stat} • Level {user_data['level']}"
        else:
            # Format numbers with commas
            formatted_stat = f"{stat_value:,}"
            value_text = f"{formatted_stat} {stat_name} • Level {user_data['level']}"

        embed.add_field(
            name=f"{medal}#{i} {name}",
            value=value_text,
            inline=False
        )

    # Add footer with available categories
    embed.set_footer(text="Categories: xp, level, messages, reactions, vc, session")

    await ctx.send(embed=embed)


@bot.command(name='xpconfig')
@commands.has_permissions(administrator=True)
async def xp_config(ctx):
    """Show current XP configuration (Admin only)"""
    embed = discord.Embed(title="⚙️ XP Configuration", color=discord.Color.green())
    embed.add_field(name="Bot Version", value=BOT_VERSION, inline=True)
    embed.add_field(name="XP per Message", value=XP_PER_MESSAGE, inline=True)
    embed.add_field(name="XP per Reaction", value=XP_PER_REACTION, inline=True)
    embed.add_field(name="XP per VC Minute", value=XP_PER_MINUTE_VC, inline=True)
    embed.add_field(name="Message Cooldown", value=f"{MESSAGE_COOLDOWN}s", inline=True)

    if LEVELUP_CHANNEL_ID:
        channel = ctx.guild.get_channel(LEVELUP_CHANNEL_ID)
        channel_name = channel.mention if channel else f"ID: {LEVELUP_CHANNEL_ID} (Not Found)"
        embed.add_field(name="Level-up Channel", value=channel_name, inline=True)
    else:
        embed.add_field(name="Level-up Channel", value="Context Channel (Not Configured)", inline=True)

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


@bot.command(name='version')
async def version(ctx):
    """Display the bot version"""
    embed = discord.Embed(title="🤖 Bot Information", color=discord.Color.purple())
    embed.add_field(name="Version", value=BOT_VERSION, inline=True)
    embed.add_field(name="Bot Name", value=bot.user.name, inline=True)
    await ctx.send(embed=embed)


@bot.command(name='help')
async def help_command(ctx):
    """Display all available bot commands"""
    embed = discord.Embed(
        title="📚 Bot Commands",
        description="Here are all the available commands:",
        color=discord.Color.blue()
    )

    # User Commands
    embed.add_field(
        name="👤 User Commands",
        value=(
            "**!rank** `[@user]` - View your or someone else's rank and stats\n"
            "**!vcpartners** `[@user]` - See top voice channel partners\n"
            "**!leaderboard** `[category] [page]` - View server leaderboards\n"
            "   Categories: `xp`, `level`, `messages`, `reactions`, `vc`, `session`\n"
            "**!version** - Display bot version information\n"
            "**!help** - Show this help message"
        ),
        inline=False
    )

    # Admin Commands
    embed.add_field(
        name="⚙️ Admin Commands",
        value=(
            "**!xpconfig** - View current XP configuration\n"
            "**!resetxp** `@user` - Reset a user's XP data"
        ),
        inline=False
    )

    embed.set_footer(text=f"Bot Version: {BOT_VERSION}")

    await ctx.send(embed=embed)


if __name__ == '__main__':
    # Get token from environment variable or replace with your token
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')

    if not TOKEN:
        print("ERROR: Please set DISCORD_BOT_TOKEN environment variable")
        print("Or replace the TOKEN line with: TOKEN = 'your-bot-token-here'")
    else:
        bot.run(TOKEN)