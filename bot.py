import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import yt_dlp
import asyncio

# --- 1. โหลด Token และตั้งค่า Intents (เหมือนเดิม) ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    print("Error: ไม่พบ DISCORD_TOKEN ในไฟล์ .env")
    exit()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# --- 2. (สำคัญ!) ตั้งค่า YDL (yt-dlp) (แก้หน่วง) ---
DL_OPTIONS = {
    'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'default_search': 'ytsearch',
    'source_address': '::', # <--- เปลี่ยนเป็นตัวนี้ (บังคับใช้ IPv6)
    'prefer_ffmpeg': True, 
}

# --- 3. (สำคัญ!) ตั้งค่า FFmpeg (แก้หน่วง) ---
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -ac 2 -probesize 32 -analyzeduration 0' # <--- ปรับ options ให้ประมวลผลเร็วขึ้น
}

# --- 4. ตัวแปรสำหรับเก็บสถานะ (คิว) (เหมือนเดิม) ---
server_states = {} # { guild_id: { 'queue': [], 'text_channel': <channel_obj> } }
current_song = {} # { guild_id: song_data }

# --- 5. สร้าง Bot (เหมือนเดิม) ---
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- 6. Events ของบอท (เหมือนเดิม) ---

@bot.event
async def on_ready():
    print(f'บอท {bot.user} ล็อกอินแล้วจ้า!')

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id:
        if before.channel is not None and after.channel is None:
            guild_id = before.guild.id
            if guild_id in server_states:
                del server_states[guild_id]
                current_song.pop(guild_id, None)
                print(f"บอทหลุดจากห้อง (ID: {guild_id}), ทำการล้างคิว")

# --- 7. ฟังก์ชันหลัก (Core Logic) (เหมือนเดิม) ---

async def play_next_song(guild_id: int):
    if guild_id not in server_states:
        return
        
    state = server_states[guild_id]
    
    if not state['queue']:
        await state['text_channel'].send("คิวเพลงหมดแล้วจ้า")
        current_song.pop(guild_id, None)
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        del server_states[guild_id]
        return
        
    voice_client = guild.voice_client
    if not voice_client:
        await state['text_channel'].send("บอทไม่ได้อยู่ในห้องเสียงแล้ว")
        del server_states[guild_id]
        return

    song_data = state['queue'].pop(0)
    current_song[guild_id] = song_data

    try:
        await state['text_channel'].send(f"🎶 กำลังเล่น: **{song_data['title']}**")
        
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(song_data['webpage_url'], download=False)
            audio_url = info['url']
            
    except Exception as e:
        await state['text_channel'].send(f"โอ๊ะ! เล่นเพลง `{song_data['title']}` ไม่ได้: {e}")
        await play_next_song(guild_id)
        return

    try:
        source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
        
        voice_client.play(
            source, 
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(guild_id), bot.loop) if e is None else print(f"Error: {e}")
        )
    except Exception as e:
        await state['text_channel'].send(f"เกิดปัญหาตอนเริ่มเล่น: {e}")
        await play_next_song(guild_id)

# --- 8. คำสั่ง (Commands) ---

@bot.command(name='help', help='แสดงหน้าต่างช่วยเหลือนี้')
async def help(ctx):
    embed = discord.Embed(
        title="📜 สรุปคำสั่งบอท (Help Menu) 📜",
        description="นี่คือคำสั่งทั้งหมดที่บอทเพลงนี้ทำได้ครับ",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="🎶 การเล่นเพลง (Music)",
        value=(
            "`!join`\n"
            "**วิธีใช้:** ให้บอทเข้าร่วมห้องเสียงที่คุณอยู่\n\n"
            
            "`!play [ชื่อเพลง หรือ ลิงก์]`\n"
            "**วิธีใช้:** เล่นเพลง หรือเพิ่มเข้าคิว (รองรับเพลย์ลิสต์ YouTube)\n\n"
            
            "`!leave`\n"
            "**วิธีใช้:** ให้ออกจากห้อง (และล้างคิวทั้งหมด)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⏯️ การควบคุมคิว (Queue Control)",
        value=(
            "`!stop`\n"
            "**วิธีใช้:** หยุดเพลงและล้างคิวทั้งหมด\n\n"
            
            "`!skip`\n"
            "**วิธีใช้:** ข้ามเพลงที่กำลังเล่นอยู่\n\n"
            
            "`!queue` (หรือ `!show`)\n"
            "**วิธีใช้:** ดูคิวเพลงที่รออยู่ และเพลงที่กำลังเล่น\n\n"
            
            "`!clear`\n" # <--- แก้ไขคำอธิบาย
            "**วิธีใช้:** หยุดเพลงและล้างคิวทั้งหมด (เหมือน !stop)" # <--- แก้ไขคำอธิบาย
        ),
        inline=False
    )
    
    embed.set_footer(text=f"บอทของคุณ {bot.user.name} | เรียกใช้งานโดย {ctx.author.name}")
    await ctx.send(embed=embed)

@bot.command(name='join', help='ให้บอทเข้าร่วมห้องเสียง')
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send(f'{ctx.author.name} จ๋า, คุณต้องเข้าห้องเสียงก่อนนะ')
    
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f'เข้าร่วมห้อง {channel} แล้ว!')

@bot.command(name='leave', help='ให้บอทออกจากห้องเสียง (และล้างคิว)')
async def leave(ctx):
    guild_id = ctx.guild.id
    
    server_states.pop(guild_id, None)
    current_song.pop(guild_id, None)

    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send('ไปแล้วนะ บ๊ายบาย!')
    else:
        await ctx.send('บอทไม่ได้อยู่ในห้องเสียงไหนเลย')

@bot.command(name='play', help='เล่นเพลง หรือ เพิ่มเพลงเข้าคิว (รองรับเพลย์ลิสต์)')
async def play(ctx, *, search: str):
    guild_id = ctx.guild.id

    if not ctx.author.voice:
        return await ctx.send("คุณต้องอยู่ในห้องเสียงก่อน ถึงจะสั่งเล่นเพลงได้")

    if ctx.voice_client is None:
        await ctx.invoke(bot.get_command('join'))
    
    if guild_id not in server_states:
        server_states[guild_id] = {
            'queue': [],
            'text_channel': ctx.channel
        }
    state = server_states[guild_id]

    await ctx.send(f'🔎 กำลังค้นหา: `{search}`...')
    
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(search, download=False)
    except Exception as e:
        return await ctx.send(f"โอ๊ะ! หาเพลงไม่เจอ หรือเกิดข้อผิดพลาด: {e}")

    added_count = 0
    
    if 'entries' in info:
        # --- กรณีเป็นเพลย์ลิสต์ ---
        for entry in info['entries']:
            if entry and entry.get('webpage_url'):
                song_data = {
                    'title': entry.get('title', 'เพลงไม่มีชื่อ'), 
                    'webpage_url': entry['webpage_url']
                }
                state['queue'].append(song_data)
                added_count += 1
        
        await ctx.send(f"✅ เพิ่ม **{added_count}** เพลงจากเพลย์ลิสต์ `{info['title']}` เข้าคิวแล้ว!")

    else:
        # --- กรณีเป็นเพลงเดียว ---
        if info.get('webpage_url'):
            song_data = {
                'title': info.get('title', 'เพลงไม่มีชื่อ'), 
                'webpage_url': info['webpage_url']
            }
            state['queue'].append(song_data)
            await ctx.send(f"✅ เพิ่ม `{song_data['title']}` เข้าคิวแล้ว!")
            added_count = 1
            
    if added_count > 0 and not ctx.voice_client.is_playing():
        await play_next_song(guild_id)

@bot.command(name='skip', help='ข้ามเพลงที่กำลังเล่นอยู่')
async def skip(ctx):
    voice_client = ctx.voice_client
    if not voice_client or not voice_client.is_playing():
        return await ctx.send("บอทไม่ได้เล่นเพลงอยู่จ้า")
    
    voice_client.stop()
    await ctx.send("⏭️ ข้ามเพลงแล้วจ้า")

@bot.command(name='stop', help='หยุดเพลงและล้างคิวทั้งหมด')
async def stop(ctx):
    guild_id = ctx.guild.id
    
    if guild_id in server_states:
        server_states[guild_id]['queue'].clear()
    current_song.pop(guild_id, None)
    
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        
    await ctx.send("⏹️ หยุดเพลงและล้างคิวทั้งหมดแล้วจ้า")

# --- (แก้ไขคำสั่ง !clear) ---
@bot.command(name='clear', help='หยุดเพลงและล้างคิวทั้งหมด (เหมือน !stop)', aliases=['stopall'])
async def clear(ctx):
    """
    ทำให้ !clear ทำงานเหมือน !stop
    เราแค่เรียกใช้ฟังก์ชัน stop(ctx) ซ้ำเลย
    """
    await ctx.send("🧹 กำลังล้างคิวและหยุดเพลงทั้งหมด...")
    await stop(ctx) # <--- เรียกใช้คำสั่ง !stop โดยตรง
# --- (จบคำสั่งใหม่) ---

@bot.command(name='queue', help='แสดงคิวเพลงที่รอเล่น (ใช้ !show ก็ได้)', aliases=['show'])
async def queue(ctx):
    guild_id = ctx.guild.id
    
    embed = discord.Embed(title="📜 คิวเพลงทั้งหมด 📜", color=discord.Color.blue())
    
    if guild_id in current_song and current_song[guild_id]:
        embed.add_field(
            name="🎶 กำลังเล่น (Now Playing)", 
            value=f"**{current_song[guild_id]['title']}**", 
            inline=False
        )
    
    if guild_id in server_states and server_states[guild_id]['queue']:
        queue_list = []
        q = server_states[guild_id]['queue']
        
        for i, song in enumerate(q[:10]):
            queue_list.append(f"`{i+1}.` {song['title']}")
        
        embed.add_field(
            name=f"⏳ คิวถัดไป ({len(q)} เพลง)",
            value="\n".join(queue_list) or "ไม่มี",
            inline=False
        )
        
        if len(q) > 10:
            embed.set_footer(text=f"และอีก {len(q) - 10} เพลง...")
    
    if not embed.fields:
        return await ctx.send("คิวว่างจ้า 텅~")
        
    await ctx.send(embed=embed)


# --- 9. รันบอท ---
if __name__ == "__main__":
    bot.run(TOKEN)