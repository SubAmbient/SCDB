import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import hashlib
import re
from typing import Optional

# Bot version
BOT_VERSION = "0.4.0"

# Load environment variables from .env file
load_dotenv()

# Get levelup channel ID from environment (optional)
LEVELUP_CHANNEL_ID = os.getenv('LEVELUP_CHANNEL_ID')
if LEVELUP_CHANNEL_ID:
    LEVELUP_CHANNEL_ID = int(LEVELUP_CHANNEL_ID)

# Get leaderboard channel ID from environment (optional)
LEADERBOARD_CHANNEL_ID = os.getenv('LEADERBOARD_CHANNEL_ID')
if LEADERBOARD_CHANNEL_ID:
    LEADERBOARD_CHANNEL_ID = int(LEADERBOARD_CHANNEL_ID)

# Bot configuration
INTENTS = discord.Intents.default()
INTENTS.message_content = True  # Required for reading message content
INTENTS.members = True  # Required for member info - MUST BE ENABLED IN DEVELOPER PORTAL
INTENTS.voice_states = True  # Required for voice tracking
INTENTS.guilds = True
INTENTS.reactions = True
INTENTS.presences = True  # Required for game/activity tracking - MUST BE ENABLED IN DEVELOPER PORTAL

bot = commands.Bot(command_prefix='!', intents=INTENTS, help_command=None)

# Configuration files
CONFIG_FILE = 'config.json'
DB_FILE = 'data.json'

# Default XP Configuration
DEFAULT_CONFIG = {
    'xp_per_message': 5,
    'xp_per_reaction': 5,
    'xp_per_minute_vc': 2,
    'message_cooldown': 10,
    'excluded_favword_channels': []
}

def load_stop_words(filepath='stop_words.json'):
    """Load stop words from JSON file, falling back to an empty set if missing"""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM automatically
            data = json.load(f)
        words = set()
        for language_list in data.values():
            words.update(w.lower() for w in language_list)
        return words
    else:
        print(f"Warning: {filepath} not found, favorite_word tracking will not filter stop words")
        return set()

# Common words to exclude from favorite_word tracking
STOP_WORDS = load_stop_words()

# Store the leaderboard message ID for updating
leaderboard_message = None

# Cache for rank calculations
_rank_cache = {}
_rank_cache_hash = None


def classify_activity(hourly_messages: dict) -> str:
    """
    Return an activity-type label based on which time bucket
    contains the most message activity.
    """
    if not hourly_messages:
        return "❓ Unknown"

    buckets = {
        'early_bird': set(range(5, 12)),
        'afternoon':  set(range(12, 18)),
        'evening':    set(range(18, 23)),
        'night_owl':  set(range(23, 24)) | set(range(0, 5)),
    }

    scores = {k: 0 for k in buckets}
    for hour_str, count in hourly_messages.items():
        hour = int(hour_str)
        for bucket, hours in buckets.items():
            if hour in hours:
                scores[bucket] += count
                break

    peak = max(scores, key=scores.get)
    labels = {
        'early_bird': '🌅 Early Bird',
        'afternoon':  '☀️ Day Person',
        'evening':    '🌆 Evening Person',
        'night_owl':  '🦉 Night Owl',
    }
    return labels[peak]


def format_peak_hour(hourly_dict: dict) -> Optional[str]:
    """
    Return the peak hour from an {hour_str: value} dict
    formatted as a 12-hour clock string (e.g. '3pm', '11am').
    Returns None if the dict is empty.
    """
    if not hourly_dict:
        return None
    peak_hour = int(max(hourly_dict, key=hourly_dict.get))
    if peak_hour == 0:
        return "12am"
    elif peak_hour < 12:
        return f"{peak_hour}am"
    elif peak_hour == 12:
        return "12pm"
    else:
        return f"{peak_hour - 12}pm"


def build_hourly_bar(hourly_dict: dict, label: str) -> str:
    """
    Build a compact 24-column text bar chart for an hourly dict.
    Each column represents one hour (0-23).
    Used by the !activity command.
    """
    if not hourly_dict:
        return f"{label}: no data yet"

    max_val = max(hourly_dict.values()) or 1
    bars = ""
    for h in range(24):
        val = hourly_dict.get(str(h), 0)
        # Scale to 0-8 using block elements
        level = round((val / max_val) * 8)
        blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        bars += blocks[level - 1] if level > 0 else " "

    return f"{label}\n`{bars}`\n`0  3  6  9  12 15 18 21 `"\


# Load or create config
def load_config():
    """Load configuration from JSON file, create if doesn't exist"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
        # Migration: ensure excluded_favword_channels exists in older config files
        if 'excluded_favword_channels' not in cfg:
            cfg['excluded_favword_channels'] = []
            with open(CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=4)
        return cfg
    else:
        # Create config file with defaults
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print(f"Created {CONFIG_FILE} with default values")
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    """Save configuration to JSON file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=4)


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
game_session_starts = {}  # Track when users start playing a game {guild_user_key: (datetime, game_name)}


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
            'vc_joins': 0,                # Number of times user has joined a voice channel
            'vc_partners': {},             # Time spent with each voice channel partner
            'longest_session': 0,          # Longest single VC session in seconds
            'longest_session_date': None,  # When the longest session occurred
            'favorite_channel': {},        # channel_id (str) → message count
            'favorite_vc_channel': {},     # channel_id (str) → seconds
            'total_characters_typed': 0,   # Total characters across all messages
            'favorite_word': {},           # word → count (stop words excluded)
            'hourly_messages': {},         # hour str (0-23) → message count
            'mentions_received': 0,        # Times this user was @mentioned by others
            'hourly_vc': {},               # hour str (0-23) → vc seconds
            'games_played': {},            # game_name → seconds played
        }
    else:
        # Update username if provided (in case user changed their name)
        if username:
            data[guild_id][user_id]['username'] = username

        # Migrations: ensure all fields exist for existing users
        user = data[guild_id][user_id]
        if 'vc_partners' not in user:
            user['vc_partners'] = {}
        if 'vc_joins' not in user:
            user['vc_joins'] = 0
        if 'longest_session' not in user:
            user['longest_session'] = 0
        if 'longest_session_date' not in user:
            user['longest_session_date'] = None
        if 'favorite_channel' not in user:
            user['favorite_channel'] = {}
        if 'favorite_vc_channel' not in user:
            user['favorite_vc_channel'] = {}
        if 'total_characters_typed' not in user:
            user['total_characters_typed'] = 0
        if 'favorite_word' not in user:
            user['favorite_word'] = {}
        if 'hourly_messages' not in user:
            user['hourly_messages'] = {}
        if 'mentions_received' not in user:
            user['mentions_received'] = 0
        if 'hourly_vc' not in user:
            user['hourly_vc'] = {}
        if 'games_played' not in user:
            user['games_played'] = {}

    return data[guild_id][user_id]


def extract_words(content):
    """Extract meaningful words from a message, stripping mentions, URLs, and punctuation"""
    # Remove URLs
    content = re.sub(r'https?://\S+', '', content)
    # Remove Discord mentions (<@id>, <#id>, <@&id>)
    content = re.sub(r'<[@#&!][^>]+>', '', content)
    # Remove custom emoji (<:name:id>)
    content = re.sub(r'<a?:[^:]+:\d+>', '', content)
    # Lowercase and extract only alphabetic words
    words = re.findall(r"[a-z']{2,}", content.lower())
    # Filter out stop words and pure-apostrophe artifacts
    return [w for w in words if w not in STOP_WORDS and w.strip("'")]


def get_cached_rank(guild_id, user_id, guild_data):
    """Get rank with caching to avoid repeated sorting"""
    global _rank_cache, _rank_cache_hash

    guild_id = str(guild_id)
    user_id = str(user_id)

    # Create hash of current data for this guild
    data_hash = hashlib.md5(json.dumps(guild_data, sort_keys=True).encode()).hexdigest()

    # If data changed, invalidate cache and rebuild
    if data_hash != _rank_cache_hash:
        _rank_cache = {}
        _rank_cache_hash = data_hash
        sorted_users = sorted(guild_data.items(), key=lambda x: x[1].get('xp', 0), reverse=True)
        for i, (uid, _) in enumerate(sorted_users, 1):
            _rank_cache[uid] = i

    return _rank_cache.get(user_id, 0)


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


def create_leaderboard_embed(guild, guild_data):
    """Create the leaderboard embed"""
    if not guild_data:
        embed = discord.Embed(
            title=f"🏆 {guild.name} - Live Leaderboard",
            description="No XP data available yet!",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Updates every 10 seconds • Bot v{BOT_VERSION}")
        return embed

    # Sort by XP
    sorted_users = sorted(guild_data.items(), key=lambda x: x[1].get('xp', 0), reverse=True)

    embed = discord.Embed(
        title=f"🏆 {guild.name} - Live Leaderboard",
        description=f"All Members by XP ({len(sorted_users)} total)",
        color=discord.Color.gold()
    )

    # Show all users
    for i, (user_id, user_data) in enumerate(sorted_users, 1):
        # Use cached member lookup (no API call)
        member = guild.get_member(int(user_id))
        name = member.display_name if member else user_data.get('username', f"User {user_id}")

        medal = ""
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "

        xp = user_data.get('xp', 0)
        level = user_data.get('level', 1)
        messages = user_data.get('messages', 0)
        vc_time = format_time(user_data.get('vc_seconds', 0))

        value_text = (
            f"**Level {level}** • {xp:,} XP\n"
            f"💬 {messages:,} msgs • 🎙️ {vc_time}"
        )

        embed.add_field(
            name=f"{medal}#{i} {name}",
            value=value_text,
            inline=False
        )

    # Add timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    embed.set_footer(text=f"Last updated: {timestamp} • Updates every 10 seconds • Bot v{BOT_VERSION}")

    return embed


@tasks.loop(seconds=10)
async def update_leaderboard():
    """Update the leaderboard message every 10 seconds"""
    global leaderboard_message

    if not LEADERBOARD_CHANNEL_ID:
        return

    # Load current data
    data = load_data()

    for guild in bot.guilds:
        channel = guild.get_channel(LEADERBOARD_CHANNEL_ID)
        if not channel:
            continue

        if not channel.permissions_for(guild.me).send_messages:
            continue

        guild_data = data.get(str(guild.id), {})
        embed = create_leaderboard_embed(guild, guild_data)

        try:
            # If we don't have a message yet, create one
            if leaderboard_message is None:
                # Check if there's an existing message by searching recent messages
                async for msg in channel.history(limit=1):
                    if msg.author == bot.user and msg.embeds and "Live Leaderboard" in msg.embeds[0].title:
                        leaderboard_message = msg
                        break

                # If still no message, create a new one
                if leaderboard_message is None:
                    leaderboard_message = await channel.send(embed=embed)
                else:
                    await leaderboard_message.edit(embed=embed)
            else:
                # Update existing message
                await leaderboard_message.edit(embed=embed)

        except discord.NotFound:
            # Message was deleted, create a new one
            leaderboard_message = await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"Error updating leaderboard: {e}")
            # If we hit rate limits or other errors, wait a bit
            await asyncio.sleep(5)


@bot.event
async def on_ready():
    print(f'Bot Version: {BOT_VERSION}')
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')

    if LEVELUP_CHANNEL_ID:
        print(f'Level-up messages will be sent to channel ID: {LEVELUP_CHANNEL_ID}')
    else:
        print('No level-up channel configured - messages will be sent in context channel')

    if LEADERBOARD_CHANNEL_ID:
        print(f'Live leaderboard will be posted in channel ID: {LEADERBOARD_CHANNEL_ID}')
    else:
        print('No leaderboard channel configured - use !setleaderboard to set one')

    # Cache all members from all guilds
    print('Caching members from all guilds...')
    total_members = 0
    for guild in bot.guilds:
        # Fetch all members to populate the cache
        async for member in guild.fetch_members(limit=None):
            total_members += 1
    print(f'Cached {total_members} members across {len(bot.guilds)} guilds')

    # Initialize voice_join_times for users already in voice channels
    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            for member in voice_channel.members:
                if not member.bot:
                    user_key = f"{guild.id}_{member.id}"
                    voice_join_times[user_key] = datetime.now()
                    voice_session_starts[user_key] = datetime.now()

    check_voice_xp.start()

    # Start the leaderboard update task if channel is configured
    if LEADERBOARD_CHANNEL_ID:
        update_leaderboard.start()


@bot.event
async def on_member_join(member):
    """Cache member when they join the server"""
    # Member is automatically added to cache by discord.py, but we can log it
    print(f'New member joined and cached: {member} in {member.guild.name}')


@bot.event
async def on_presence_update(before, after):
    """Track game activity for favorite game stats"""
    if after.bot:
        return

    user_key = f"{after.guild.id}_{after.id}"
    now = datetime.now()

    # Determine the game being played before and after the update
    def get_game(member):
        for activity in member.activities:
            if isinstance(activity, discord.Game):
                return activity.name
            if isinstance(activity, discord.Activity) and activity.type == discord.ActivityType.playing:
                return activity.name
        return None

    game_before = get_game(before)
    game_after = get_game(after)

    # If the game changed (stopped, started, or switched)
    if game_before != game_after:
        # Stop tracking the previous game and save the session
        if game_before and user_key in game_session_starts:
            session_start, tracked_game = game_session_starts.pop(user_key)
            seconds_played = int((now - session_start).total_seconds())
            if seconds_played > 0:
                data = load_data()
                user_data = get_user_data(data, after.guild.id, after.id, str(after))
                user_data['games_played'][tracked_game] = (
                    user_data['games_played'].get(tracked_game, 0) + seconds_played
                )
                save_data(data)

        # Start tracking the new game
        if game_after:
            game_session_starts[user_key] = (now, game_after)


@bot.event
async def on_message(message):
    """Award XP for messages"""
    # Ignore bot messages
    if message.author.bot:
        await bot.process_commands(message)
        return

    user_key = f"{message.guild.id}_{message.author.id}"
    current_time = datetime.now()
    current_hour = str(current_time.hour)  # "0" – "23"

    # Skip all tracking if the channel is excluded
    excluded_channels = config.get('excluded_favword_channels', [])
    if message.channel.id in excluded_channels:
        await bot.process_commands(message)
        return

    # Load data once for this message
    data = load_data()
    user_data = get_user_data(data, message.guild.id, message.author.id, str(message.author))

    # Track favorite words (not commands)
    if not message.content.startswith(bot.command_prefix):
        for word in extract_words(message.content):
            user_data['favorite_word'][word] = user_data['favorite_word'].get(word, 0) + 1

    # Check cooldown — save word tracking and bail out early if on cooldown
    if user_key in message_cooldowns:
        if current_time - message_cooldowns[user_key] < timedelta(seconds=MESSAGE_COOLDOWN):
            save_data(data)  # Persist the word tracking recorded above
            await bot.process_commands(message)
            return

    # Update cooldown
    message_cooldowns[user_key] = current_time

    # Award XP and update stats
    old_level = user_data['level']
    user_data['xp'] += XP_PER_MESSAGE
    user_data['messages'] += 1
    user_data['level'] = calculate_level(user_data['xp'])

    # Favorite channel: increment count for this channel
    channel_id = str(message.channel.id)
    user_data['favorite_channel'][channel_id] = user_data['favorite_channel'].get(channel_id, 0) + 1

    # Total characters typed (raw message content length)
    user_data['total_characters_typed'] += len(message.content)

    user_data['hourly_messages'][current_hour] = (
        user_data['hourly_messages'].get(current_hour, 0) + 1
    )

    # Track mentions received by other users
    for mentioned in message.mentions:
        if mentioned.bot or mentioned.id == message.author.id:
            continue
        mentioned_data = get_user_data(data, message.guild.id, mentioned.id, str(mentioned))
        mentioned_data['mentions_received'] = mentioned_data.get('mentions_received', 0) + 1

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

        # Increment vc_joins counter (no XP awarded, tracking only)
        data = load_data()
        user_data = get_user_data(data, member.guild.id, member.id, str(member))
        user_data['vc_joins'] += 1
        save_data(data)

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
    current_hour = str(datetime.now().hour)

    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            # Count non-bot, non-muted members in the channel
            non_bot_members = [m for m in voice_channel.members if
                               not m.bot and not m.voice.self_mute and not m.voice.mute]

            # Skip if only one person (or no one) is in the channel
            if len(non_bot_members) <= 1:
                continue

            channel_id = str(voice_channel.id)

            for member in non_bot_members:
                user_key = f"{guild.id}_{member.id}"
                if user_key in voice_join_times:
                    # Award XP for 1 minute (60 seconds)
                    user_data = get_user_data(data, guild.id, member.id, str(member))
                    old_level = user_data['level']

                    user_data['xp'] += XP_PER_MINUTE_VC
                    user_data['vc_seconds'] += 60
                    user_data['level'] = calculate_level(user_data['xp'])

                    # Favorite VC channel: accumulate seconds per channel
                    user_data['favorite_vc_channel'][channel_id] = (
                        user_data['favorite_vc_channel'].get(channel_id, 0) + 60
                    )

                    user_data['hourly_vc'][current_hour] = (
                        user_data['hourly_vc'].get(current_hour, 0) + 60
                    )

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


@bot.command(name='excludechannel')
@commands.has_permissions(administrator=True)
async def exclude_channel(ctx, channel: discord.TextChannel = None):
    """Exclude a channel from all XP and stat tracking (Admin only).

    Usage: !excludechannel [#channel]
    Omit #channel to exclude the current channel.
    """
    start_time = time.perf_counter()
    target = channel or ctx.channel

    excluded = config.setdefault('excluded_favword_channels', [])

    if target.id in excluded:
        msg = await ctx.send(
            f"⚠️ {target.mention} is already excluded from favwords tracking.\n⚡ Calculating..."
        )
    else:
        excluded.append(target.id)
        save_config(config)
        msg = await ctx.send(
            f"✅ {target.mention} has been excluded from all XP and stat tracking. "
            f"Messages there will no longer count towards anything.\n⚡ Calculating..."
        )

    response_time = (time.perf_counter() - start_time) * 1000
    await msg.edit(content=msg.content.replace("⚡ Calculating...", f"⚡ {response_time:.0f}ms"))


@bot.command(name='includechannel')
@commands.has_permissions(administrator=True)
async def include_channel(ctx, channel: discord.TextChannel = None):
    """Re-include a previously excluded channel in all XP and stat tracking (Admin only).

    Usage: !includechannel [#channel]
    Omit #channel to re-include the current channel.
    """
    start_time = time.perf_counter()
    target = channel or ctx.channel

    excluded = config.setdefault('excluded_favword_channels', [])

    if target.id not in excluded:
        msg = await ctx.send(
            f"⚠️ {target.mention} is not currently excluded from tracking.\n⚡ Calculating..."
        )
    else:
        excluded.remove(target.id)
        save_config(config)
        msg = await ctx.send(
            f"✅ {target.mention} has been re-included in all XP and stat tracking. "
            f"Messages there will count again.\n⚡ Calculating..."
        )

    response_time = (time.perf_counter() - start_time) * 1000
    await msg.edit(content=msg.content.replace("⚡ Calculating...", f"⚡ {response_time:.0f}ms"))


@bot.command(name='excludedchannels')
@commands.has_permissions(administrator=True)
async def list_excluded_channels(ctx):
    """List all channels currently excluded from favwords tracking (Admin only)."""
    start_time = time.perf_counter()

    excluded = config.get('excluded_favword_channels', [])

    embed = discord.Embed(
        title="🚫 Channels Excluded from All Tracking",
        color=discord.Color.red()
    )

    if not excluded:
        embed.description = "No channels are currently excluded."
        embed.set_footer(text="⚡ Calculating...")
    else:
        lines = []
        for ch_id in excluded:
            ch = ctx.guild.get_channel(ch_id)
            lines.append(ch.mention if ch else f"Unknown channel (ID: {ch_id})")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"{len(excluded)} excluded channel(s) • ⚡ Calculating...")

    msg = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000

    footer = embed.footer.text.replace("⚡ Calculating...", f"⚡ {response_time:.0f}ms")
    embed.set_footer(text=footer)
    await msg.edit(embed=embed)


# ---------------------------------------------------------------------------
# Existing admin / user commands
# ---------------------------------------------------------------------------

@bot.command(name='setleaderboard')
@commands.has_permissions(administrator=True)
async def set_leaderboard(ctx):
    """Set the current channel as the live leaderboard channel (Admin only)"""
    start_time = time.perf_counter()
    global leaderboard_message, LEADERBOARD_CHANNEL_ID

    LEADERBOARD_CHANNEL_ID = ctx.channel.id

    # Clear old message reference
    leaderboard_message = None

    # Start the update task if not already running
    if not update_leaderboard.is_running():
        update_leaderboard.start()

    # Immediately post the first leaderboard
    data = load_data()
    guild_data = data.get(str(ctx.guild.id), {})
    embed = create_leaderboard_embed(ctx.guild, guild_data)

    # Send initial response message
    response_msg = await ctx.send(
        f"✅ Live leaderboard set to {ctx.channel.mention}! It will update every 10 seconds.\n⚡ Calculating...")

    # Send the leaderboard
    leaderboard_message = await ctx.channel.send(embed=embed)

    # Calculate total response time and update the message
    response_time = (time.perf_counter() - start_time) * 1000
    await response_msg.edit(
        content=f"✅ Live leaderboard set to {ctx.channel.mention}! It will update every 10 seconds.\n⚡ {response_time:.0f}ms")


@bot.command(name='profile')
async def profile(ctx, member: discord.Member = None):
    """Show comprehensive profile for yourself or another user"""
    start_time = time.perf_counter()
    member = member or ctx.author

    data = load_data()
    user_data = get_user_data(data, ctx.guild.id, member.id)

    # Calculate rank using cached function
    guild_data = data.get(str(ctx.guild.id), {})
    rank = get_cached_rank(ctx.guild.id, member.id, guild_data)

    # Calculate XP for next level
    next_level_xp = xp_for_next_level(user_data['level'])
    xp_progress = user_data['xp'] - xp_for_next_level(user_data['level'] - 1)
    xp_needed = next_level_xp - xp_for_next_level(user_data['level'] - 1)
    progress_percentage = int((xp_progress / xp_needed) * 100) if xp_needed > 0 else 100

    # Wider, nicer progress bar (20 chars)
    bar_length = 20
    filled = int((xp_progress / xp_needed) * bar_length) if xp_needed > 0 else bar_length
    progress_bar = "▰" * filled + "▱" * (bar_length - filled)

    # Pick embed color from rank
    if rank == 1:
        embed_color = discord.Color.from_rgb(255, 215, 0)    # Gold
    elif rank == 2:
        embed_color = discord.Color.from_rgb(192, 192, 192)  # Silver
    elif rank == 3:
        embed_color = discord.Color.from_rgb(205, 127, 50)   # Bronze
    else:
        embed_color = discord.Color.from_rgb(114, 137, 218)  # Discord blurple

    embed = discord.Embed(
        color=embed_color
    )
    embed.set_author(name=f"{member.display_name}'s Profile", icon_url=member.display_avatar.url)
    embed.set_thumbnail(url=member.display_avatar.url)

    # ── Row 1: Rank / Level / XP ──────────────────────────────────────────
    embed.add_field(name="📊  Rank",     value=f"**#{rank}**",                    inline=True)
    embed.add_field(name="⭐  Level",    value=f"**{user_data['level']}**",        inline=True)
    embed.add_field(name="🏆  Total XP", value=f"**{user_data['xp']:,}**",        inline=True)

    # ── Progress bar ──────────────────────────────────────────────────────
    embed.add_field(
        name="📈  Progress to Level " + str(user_data['level'] + 1),
        value=f"`{progress_bar}` **{progress_percentage}%**\n"
              f"{xp_progress:,} / {xp_needed:,} XP",
        inline=False
    )

    # ── Blank row separator ───────────────────────────────────────────────
    embed.add_field(name="\u200b", value="\u200b", inline=False)

    # ── Row 2: Messages / Reactions / VC Time ─────────────────────────────
    embed.add_field(name="💬  Messages",  value=f"{user_data['messages']:,}",                      inline=True)
    embed.add_field(name="❤️  Reactions", value=f"{user_data['reactions']:,}",                     inline=True)
    embed.add_field(name="🎙️  VC Time",   value=format_time(user_data.get('vc_seconds', 0)),       inline=True)

    # ── Row 3: Mentions / Activity Type / Peak VC Hour ────────────────────
    mentions = user_data.get('mentions_received', 0)
    activity_type = classify_activity(user_data.get('hourly_messages', {}))
    peak_vc = format_peak_hour(user_data.get('hourly_vc', {}))

    embed.add_field(name="📣  Mentioned",    value=f"{mentions:,}",  inline=True)
    embed.add_field(name="🕐  Activity Type", value=activity_type,   inline=True)
    embed.add_field(name="🔊  Peak VC Hour",  value=peak_vc or "—",  inline=True)

    # ── Row 4: Avg Daily VC + Longest Session (pair, padded to 3) ─────────
    bot_joined = ctx.guild.me.joined_at
    if bot_joined:
        days_since_join = max((datetime.now(bot_joined.tzinfo) - bot_joined).days, 1)
        avg_daily_vc = user_data.get('vc_seconds', 0) / days_since_join
        embed.add_field(name="📅  Avg Daily VC", value=format_time(int(avg_daily_vc)), inline=True)

    longest_session = user_data.get('longest_session', 0)
    if longest_session > 0:
        longest_str = format_time(longest_session)
        session_date = user_data.get('longest_session_date')
        if session_date:
            try:
                date_obj = datetime.fromisoformat(session_date)
                date_str = date_obj.strftime("%Y-%m-%d")
                longest_val = f"{longest_str}\n`{date_str}`"
            except:
                longest_val = longest_str
        else:
            longest_val = longest_str
        embed.add_field(name="⏱️  Longest Session", value=longest_val, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # pad to 3
    elif bot_joined:
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

    # ── Top VC Partners ───────────────────────────────────────────────────
    vc_partners = user_data.get('vc_partners', {})
    if vc_partners:
        sorted_partners = sorted(vc_partners.items(), key=lambda x: x[1]['seconds'], reverse=True)
        top_3_parts = []
        medals = ["🥇", "🥈", "🥉"]
        for idx, (partner_id, partner_data) in enumerate(sorted_partners[:3]):
            time_str = format_time(partner_data['seconds'])
            partner_member = ctx.guild.get_member(int(partner_id))
            partner_name = partner_member.display_name if partner_member else partner_data.get('username', f'User {partner_id}')
            top_3_parts.append(f"{medals[idx]} **{partner_name}** — {time_str}")

        embed.add_field(
            name="🤝  Top VC Partners",
            value="\n".join(top_3_parts),
            inline=False
        )

    # ── Current Game + Favorite Game ──────────────────────────────────────
    def get_current_game(m):
        for activity in m.activities:
            if isinstance(activity, discord.Game):
                return activity.name
            if isinstance(activity, discord.Activity) and activity.type == discord.ActivityType.playing:
                return activity.name
        return None

    current_game = get_current_game(member)
    games_played = user_data.get('games_played', {})

    if current_game or games_played:
        if current_game:
            embed.add_field(name="🎮  Now Playing", value=f"**{current_game}**", inline=True)
        if games_played:
            fav_game = max(games_played, key=games_played.get)
            fav_game_time = format_time(games_played[fav_game])
            embed.add_field(name="🏅  Favorite Game", value=f"**{fav_game}**\n{fav_game_time} played", inline=True)
            if current_game:
                embed.add_field(name="\u200b", value="\u200b", inline=True)  # pad to 3

    embed.set_footer(text="⚡ Calculating...")

    # Send message and measure total time
    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000

    # Update footer with actual response time
    embed.set_footer(text=f"⚡ {response_time:.0f}ms")
    await message.edit(embed=embed)


@bot.command(name='rank')
async def rank(ctx, member: discord.Member = None):
    """Check your or someone else's rank"""
    start_time = time.perf_counter()
    member = member or ctx.author

    data = load_data()
    user_data = get_user_data(data, ctx.guild.id, member.id)

    # Calculate rank using cached function
    guild_data = data.get(str(ctx.guild.id), {})
    rank = get_cached_rank(ctx.guild.id, member.id, guild_data)

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

    embed.set_footer(text="⚡ Calculating...")

    # Send message and measure total time
    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000

    # Update footer with actual response time
    embed.set_footer(text=f"⚡ {response_time:.0f}ms")
    await message.edit(embed=embed)


@bot.command(name='activity')
async def activity(ctx, member: discord.Member = None):
    """
    Show hourly activity charts for messages and voice time.

    Usage: !activity [@user]
    """
    start_time = time.perf_counter()
    member = member or ctx.author

    data = load_data()
    user_data = get_user_data(data, ctx.guild.id, member.id)

    hourly_messages = user_data.get('hourly_messages', {})
    hourly_vc = user_data.get('hourly_vc', {})
    activity_type = classify_activity(hourly_messages)
    peak_msg_hour = format_peak_hour(hourly_messages)
    peak_vc_hour = format_peak_hour(hourly_vc)

    embed = discord.Embed(
        title=f"📊 {member.display_name}'s Activity Patterns",
        color=discord.Color.og_blurple()
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    # Activity classification
    embed.add_field(name="🕐 Activity Type", value=activity_type, inline=True)
    if peak_msg_hour:
        embed.add_field(name="💬 Peak Message Hour", value=peak_msg_hour, inline=True)
    if peak_vc_hour:
        embed.add_field(name="🎙️ Peak VC Hour", value=peak_vc_hour, inline=True)

    # Hourly bar charts
    msg_bar = build_hourly_bar(hourly_messages, "💬 Messages by hour")
    embed.add_field(name="\u200b", value=msg_bar, inline=False)

    if hourly_vc:
        vc_bar = build_hourly_bar(hourly_vc, "🎙️ VC time by hour")
        embed.add_field(name="\u200b", value=vc_bar, inline=False)

    # Time zone note
    embed.set_footer(text="Times are in the server's local timezone • ⚡ Calculating...")

    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000
    embed.set_footer(text=f"Times are in the server's local timezone • ⚡ {response_time:.0f}ms")
    await message.edit(embed=embed)


@bot.command(name='vcpartners')
async def vc_partners(ctx, member: discord.Member = None):
    """Show who you've spent the most time with in voice channels"""
    start_time = time.perf_counter()
    member = member or ctx.author

    data = load_data()
    user_data = get_user_data(data, ctx.guild.id, member.id)

    vc_partners = user_data.get('vc_partners', {})

    if not vc_partners:
        message = await ctx.send(f"{member.display_name} hasn't spent time in voice channels with anyone yet!")
        response_time = (time.perf_counter() - start_time) * 1000
        await message.edit(
            content=f"{member.display_name} hasn't spent time in voice channels with anyone yet!\n⚡ {response_time:.0f}ms")
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

        # Use cached member lookup instead of fetch
        partner_member = ctx.guild.get_member(int(partner_id))
        partner_name = partner_member.display_name if partner_member else partner_data.get('username',
                                                                                           f'User {partner_id}')

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
    footer_text = "⚡ Calculating..."
    if total_partners > 10:
        footer_text = f"Showing top 10 of {total_partners} partners • {footer_text}"

    embed.set_footer(text=footer_text)

    # Send message and measure total time
    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000

    # Update footer with actual response time
    footer_text = f"⚡ {response_time:.0f}ms"
    if total_partners > 10:
        footer_text = f"Showing top 10 of {total_partners} partners • {footer_text}"
    embed.set_footer(text=footer_text)
    await message.edit(embed=embed)


@bot.command(name='favwords')
async def fav_words(ctx, member: discord.Member = None):
    """Show a user's top 5 most used words"""
    start_time = time.perf_counter()
    member = member or ctx.author

    data = load_data()
    user_data = get_user_data(data, ctx.guild.id, member.id)

    favorite_word = user_data.get('favorite_word', {})

    if not favorite_word:
        message = await ctx.send(f"{member.display_name} hasn't sent enough messages to track words yet!")
        response_time = (time.perf_counter() - start_time) * 1000
        await message.edit(content=f"{member.display_name} hasn't sent enough messages to track words yet!\n⚡ {response_time:.0f}ms")
        return

    sorted_words = sorted(favorite_word.items(), key=lambda x: x[1], reverse=True)[:5]

    embed = discord.Embed(
        title=f"💬 {member.display_name}'s Favorite Words",
        description="Top 5 most used words (common words excluded)",
        color=discord.Color.teal()
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, (word, count) in enumerate(sorted_words):
        embed.add_field(
            name=f"{medals[i]} #{i+1} \"{word}\"",
            value=f"Used **{count:,}** time{'s' if count != 1 else ''}",
            inline=False
        )

    embed.set_footer(text="⚡ Calculating...")

    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000
    embed.set_footer(text=f"⚡ {response_time:.0f}ms")
    await message.edit(embed=embed)


@bot.command(name='leaderboard')
async def leaderboard(ctx, category: str = 'xp', page: int = 1):
    """Show the server leaderboard

    Categories: xp, level, messages, reactions, vc (voice chat time), session (longest session),
                mentions (most mentioned)
    Usage: !leaderboard [category] [page]
    Example: !leaderboard mentions 1
    """
    start_time = time.perf_counter()
    data = load_data()
    guild_data = data.get(str(ctx.guild.id), {})

    if not guild_data:
        await ctx.send("No XP data available yet!")
        return

    # Validate and normalize category
    category = category.lower()
    valid_categories = {
        'xp':       ('xp',                '🏆 XP',               'XP'),
        'level':    ('level',             '⭐ Level',            'Level'),
        'messages': ('messages',          '💬 Messages',         'Messages'),
        'reactions':('reactions',         '❤️ Reactions',        'Reactions'),
        'vc':       ('vc_seconds',        '🎙️ Voice Time',       'Time'),
        'vctime':   ('vc_seconds',        '🎙️ Voice Time',       'Time'),
        'voice':    ('vc_seconds',        '🎙️ Voice Time',       'Time'),
        'session':  ('longest_session',   '⏱️ Longest Session',  'Session'),
        'longest':  ('longest_session',   '⏱️ Longest Session',  'Session'),
        'mentions': ('mentions_received', '📣 Most Mentioned',   'Mentions'),
    }

    if category not in valid_categories:
        await ctx.send(
            f"❌ Invalid category! Use: `xp`, `level`, `messages`, `reactions`, `vc`, `session`, or `mentions`"
        )
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
        # Use cached member lookup instead of fetch
        member = ctx.guild.get_member(int(user_id))
        name = member.display_name if member else user_data.get('username', f"User {user_id}")

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
            formatted_stat = format_time(stat_value)
            value_text = f"{formatted_stat} • Level {user_data['level']}"
        else:
            formatted_stat = f"{stat_value:,}"
            value_text = f"{formatted_stat} {stat_name} • Level {user_data['level']}"

        embed.add_field(
            name=f"{medal}#{i} {name}",
            value=value_text,
            inline=False
        )

    embed.set_footer(text="Categories: xp, level, messages, reactions, vc, session, mentions • ⚡ Calculating...")

    # Send message and measure total time
    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000

    embed.set_footer(
        text=f"Categories: xp, level, messages, reactions, vc, session, mentions • ⚡ {response_time:.0f}ms"
    )
    await message.edit(embed=embed)


@bot.command(name='xpconfig')
@commands.has_permissions(administrator=True)
async def xp_config(ctx):
    """Show current XP configuration (Admin only)"""
    start_time = time.perf_counter()

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

    if LEADERBOARD_CHANNEL_ID:
        channel = ctx.guild.get_channel(LEADERBOARD_CHANNEL_ID)
        channel_name = channel.mention if channel else f"ID: {LEADERBOARD_CHANNEL_ID} (Not Found)"
        embed.add_field(name="Live Leaderboard Channel", value=channel_name, inline=True)
    else:
        embed.add_field(name="Live Leaderboard Channel", value="Not Configured", inline=True)

    # Show excluded favword channels
    excluded = config.get('excluded_favword_channels', [])
    if excluded:
        excluded_names = []
        for ch_id in excluded:
            ch = ctx.guild.get_channel(ch_id)
            excluded_names.append(ch.mention if ch else f"ID: {ch_id}")
        embed.add_field(
            name="🚫 Excluded Channels (No Tracking)",
            value="\n".join(excluded_names),
            inline=False
        )
    else:
        embed.add_field(name="🚫 Excluded Channels (No Tracking)", value="None", inline=False)

    embed.set_footer(text="⚡ Calculating...")

    # Send message and measure total time
    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000

    # Update footer with actual response time
    embed.set_footer(text=f"⚡ {response_time:.0f}ms")
    await message.edit(embed=embed)


@bot.command(name='resetxp')
@commands.has_permissions(administrator=True)
async def reset_xp(ctx, member: discord.Member):
    """Reset a user's XP (Admin only)"""
    start_time = time.perf_counter()

    data = load_data()
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)

    if guild_id in data and user_id in data[guild_id]:
        del data[guild_id][user_id]
        save_data(data)
        message = await ctx.send(f"✅ Reset XP for {member.display_name}\n⚡ Calculating...")
        response_time = (time.perf_counter() - start_time) * 1000
        await message.edit(content=f"✅ Reset XP for {member.display_name}\n⚡ {response_time:.0f}ms")
    else:
        message = await ctx.send(f"❌ No XP data found for {member.display_name}\n⚡ Calculating...")
        response_time = (time.perf_counter() - start_time) * 1000
        await message.edit(content=f"❌ No XP data found for {member.display_name}\n⚡ {response_time:.0f}ms")


@bot.command(name='version')
async def version(ctx):
    """Display the bot version"""
    start_time = time.perf_counter()

    embed = discord.Embed(title="🤖 Bot Information", color=discord.Color.purple())
    embed.add_field(name="Version", value=BOT_VERSION, inline=True)
    embed.add_field(name="Bot Name", value=bot.user.name, inline=True)

    embed.set_footer(text="⚡ Calculating...")

    # Send message and measure total time
    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000

    # Update footer with actual response time
    embed.set_footer(text=f"⚡ {response_time:.0f}ms")
    await message.edit(embed=embed)


@bot.command(name='help')
async def help_command(ctx):
    """Display all available bot commands"""
    start_time = time.perf_counter()

    embed = discord.Embed(
        title="📚 Bot Commands",
        description="Here are all the available commands:",
        color=discord.Color.blue()
    )

    # User Commands
    embed.add_field(
        name="👤 User Commands",
        value=(
            "**!profile** `[@user]` - View comprehensive profile with stats and progress\n"
            "**!rank** `[@user]` - View your or someone else's rank and stats\n"
            "**!activity** `[@user]` - View hourly activity charts and Early Bird / Night Owl type\n"
            "**!vcpartners** `[@user]` - See top voice channel partners\n"
            "**!favwords** `[@user]` - See top 5 most used words\n"
            "**!leaderboard** `[category] [page]` - View server leaderboards\n"
            "   Categories: `xp`, `level`, `messages`, `reactions`, `vc`, `session`, `mentions`\n"
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
            "**!resetxp** `@user` - Reset a user's XP data\n"
            "**!setleaderboard** - Set current channel as live leaderboard (updates every 10s)\n"
            "**!excludechannel** `[#channel]` - Exclude a channel from all XP and stat tracking\n"
            "**!includechannel** `[#channel]` - Re-include a channel in all XP and stat tracking\n"
            "**!excludedchannels** - List all excluded channels"
        ),
        inline=False
    )

    embed.set_footer(text=f"Bot Version: {BOT_VERSION} • ⚡ Calculating...")

    # Send message and measure total time
    message = await ctx.send(embed=embed)
    response_time = (time.perf_counter() - start_time) * 1000

    # Update footer with actual response time
    embed.set_footer(text=f"Bot Version: {BOT_VERSION} • ⚡ {response_time:.0f}ms")
    await message.edit(embed=embed)


if __name__ == '__main__':
    # Get token from environment variable or replace with your token
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')

    if not TOKEN:
        print("ERROR: Please set DISCORD_BOT_TOKEN environment variable")
        print("Or replace the TOKEN line with: TOKEN = 'your-bot-token-here'")
    else:
        bot.run(TOKEN)