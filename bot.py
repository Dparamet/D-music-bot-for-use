import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import yt_dlp
import asyncio

# --- 1. โหลด Token และตั้งค่า Intents ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    print("Error: ไม่พบ DISCORD_TOKEN ในไฟล์ .env")
    exit()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# --- 2. ตั้งค่า YDL (yt-dlp) ---
YDL_OPTIONS = {
    'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'default_search': 'ytsearch',
    'source_address': '::', # บังคับใช้ IPv6
    'prefer_ffmpeg': True,
}

# --- 3. ตั้งค่า FFmpeg ---
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -ac 2 -probesize 32 -analyzeduration 0'
}

# --- 4. ตัวแปรสำหรับเก็บสถานะ (คิว) ---
server_states = {}
current_song = {}

# --- 5. สร้าง Bot ---
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- (ใหม่!) ตรวจสอบ Opus (ระบบเสียง) ---
if not discord.opus.is_loaded():
    print("!!!!!!!!!!!!")
    print("!!! คำเตือน: Opus (ระบบเสียง) ไม่ได้โหลด! บอทอาจจะเล่นเพลงไม่ได้ !!!")
    print("!!! ลองติดตั้ง: pip install discord.py[voice]")
    print("!!!!!!!!!!!!")
else:
    print(">>> Opus โหลดสำเร็จ (ระบบเสียงพร้อม)")

# --- 6. Events ของบอท ---

@bot.event
async def on_ready():
    print(f'>>> บอท {bot.user} ล็อกอินแล้วจ้า!')

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id:
        if before.channel is not None and after.channel is None:
            guild_id = before.guild.id
            if guild_id in server_states:
                del server_states[guild_id]
                current_song.pop(guild_id, None)
                print(f"!!! บอทหลุดจากห้อง (ID: {guild_id}), ทำการล้างคิว")

# --- 7. ฟังก์ชันหลัก (Core Logic) (เพิ่ม DEBUG) ---

async def play_next_song(guild_id: int):
    """
    หัวใจของระบบคิว: เล่นเพลงถัดไป (ถ้ามี)
    """
    print(f"[Debug] ฟังก์ชัน play_next_song ถูกเรียกสำหรับ Guild {guild_id}")
    if guild_id not in server_states:
        print(f"[Debug] ไม่พบ State ของ Guild {guild_id}")
        return
        
    state = server_states[guild_id]
    
    if not state['queue']:
        print("[Debug] คิวว่างเปล่า กำลังหยุด...")
        await state['text_channel'].send("คิวเพลงหมดแล้วจ้า")
        current_song.pop(guild_id, None)
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        print(f"[Debug] ไม่พบ Guild {guild_id}")
        del server_states[guild_id]
        return
        
    voice_client = guild.voice_client
    if not voice_client:
        print("[Debug] บอทไม่อยู่ในห้องเสียงแล้ว")
        await state['text_channel'].send("บอทไม่ได้อยู่ในห้องเสียงแล้ว")
        del server_states[guild_id]
        return

    # 1. ดึง "ข้อมูล" เพลงออกจากคิว
    song_data = state['queue'].pop(0)
    current_song[guild_id] = song_data
    print(f"[Debug] ดึงเพลงออกจากคิว: {song_data['title']}")

    # 2. ค้นหา "ลิงก์สตรีมสด" ณ วินาทีที่จะเล่น
    try:
        await state['text_channel'].send(f"🎶 กำลังเล่น: **{song_data['title']}**")
        print("[Debug] กำลังค้นหา YDL (yt-dlp) เพื่อเอาลิงก์สตรีม...")
        
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(song_data['webpage_url'], download=False)
            audio_url = info['url']
        
        print("[Debug] ค้นหา YDL สำเร็จ ได้ลิงก์มาแล้ว")
            
    except Exception as e:
        print(f"!!!!!!!!!!!! [Debug] YDL (ค้นหาลิงก์สตรีม) ล้มเหลว: {e}")
        await state['text_channel'].send(f"โอ๊ะ! เล่นเพลง `{song_data['title']}` ไม่ได้: {e}")
        await play_next_song(guild_id) # ลองเพลงถัดไป
        return

    # 3. สร้าง source และเล่น (นี่คือจุดที่มักจะตาย)
    try:
        print("[Debug] กำลังสร้าง FFmpegPCMAudio source... (ถ้าค้างตรงนี้ = โดนโฮสต์ฆ่า)")
        source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
        
        print("[Debug] สร้าง Source สำเร็จ กำลังสั่ง .play()...")
        voice_client.play(
            source, 
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(guild_id), bot.loop) if e is None else print(f"[Error in 'after']: {e}")
        )
        print("[Debug] สั่ง .play() สำเร็จ (เพลงควรจะเริ่ม)")
    except Exception as e:
        print(f"!!!!!!!!!!!! [Debug] FFmpeg หรือ .play() ล้มเหลว: {e}")
        await state['text_channel'].send(f"เกิดปัญหาตอนเริ่มเล่น: {e}")
        await play_next_song(guild_id)

# --- 8. คำสั่ง (Commands) (เพิ่ม DEBUG) ---

@bot.command(name='help', help='แสดงหน้าต่างช่วยเหลือนี้')
async def help(ctx):
    # (โค้ด Help เหมือนเดิม)
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
            "`!clear`\n"
            "**วิธีใช้:** หยุดเพลงและล้างคิวทั้งหมด (เหมือน !stop)"
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
    print(f"\n[Debug] คำสั่ง !play ถูกเรียก: '{search}'")

    if not ctx.author.voice:
        return await ctx.send("คุณต้องอยู่ในห้องเสียงก่อน ถึงจะสั่งเล่นเพลงได้")

    if ctx.voice_client is None:
        print("[Debug] บอทไม่ได้อยู่ในห้อง กำลังเรียก !join...")
        await ctx.invoke(bot.get_command('join'))
    
    if guild_id not in server_states:
        print(f"[Debug] สร้าง State ใหม่สำหรับ Guild {guild_id}")
        server_states[guild_id] = {
            'queue': [],
            'text_channel': ctx.channel
        }
    state = server_states[guild_id]

    await ctx.send(f'🔎 กำลังค้นหา: `{search}`...')
    print("[Debug] กำลังค้นหา YDL (สำหรับ !play)...")
    
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(search, download=False)
        print("[Debug] ค้นหา YDL (สำหรับ !play) สำเร็จ")
    except Exception as e:
        print(f"!!!!!!!!!!!! [Debug] YDL (สำหรับ !play) ล้มเหลว: {e}")
        return await ctx.send(f"โอ๊ะ! หาเพลงไม่เจอ หรือเกิดข้อผิดพลาด: {e}")

    added_count = 0
    
    if 'entries' in info:
        # --- กรณีเป็นเพลย์ลิสต์ ---
        print("[Debug] ตรวจพบเพลย์ลิสต์")
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
        print("[Debug] ตรวจพบเพลงเดียว")
        if info.get('webpage_url'):
            song_data = {
                'title': info.get('title', 'เพลงไม่มีชื่อ'), 
                'webpage_url': info['webpage_url']
            }
            state['queue'].append(song_data)
            await ctx.send(f"✅ เพิ่ม `{song_data['title']}` เข้าคิวแล้ว!")
            added_count = 1
    
    print(f"[Debug] เพิ่มเพลงเข้าคิวแล้ว {added_count} เพลง")
    if added_count > 0 and not ctx.voice_client.is_playing():
        print("[Debug] บอทว่าง กำลังเรียก play_next_song...")
        await play_next_song(guild_id)
    else:
        print("[Debug] บอทกำลังเล่นเพลงอยู่ เพลงนี้จึงเข้าคิว")


@bot.command(name='skip', help='ข้ามเพลงที่กำลังเล่นอยู่')
async def skip(ctx):
    voice_client = ctx.voice_client
    if not voice_client or not voice_client.is_playing():
        return await ctx.send("บอทไม่ได้เล่นเพลงอยู่จ้า")
    
    print("[Debug] กำลังข้ามเพลง...")
    voice_client.stop()
    await ctx.send("⏭️ ข้ามเพลงแล้วจ้า")

@bot.command(name='stop', help='หยุดเพลงและล้างคิวทั้งหมด')
async def stop(ctx):
    guild_id = ctx.guild.id
    print("[Debug] กำลังหยุดเพลงและล้างคิว...")
    
    if guild_id in server_states:
        server_states[guild_id]['queue'].clear()
    current_song.pop(guild_id, None)
    
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        
    await ctx.send("⏹️ หยุดเพลงและล้างคิวทั้งหมดแล้วจ้า")

@bot.command(name='clear', help='หยุดเพลงและล้างคิวทั้งหมด (เหมือน !stop)', aliases=['stopall'])
async def clear(ctx):
    await ctx.send("🧹 กำลังล้างคิวและหยุดเพลงทั้งหมด...")
    await stop(ctx)

@bot.command(name='queue', help='แสดงคิวเพลงที่รอเล่น (ใช้ !show ก็ได้)', aliases=['show'])
async def queue(ctx):
    # (โค้ด Queue เหมือนเดิม)
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
    print(">>> กำลังเริ่มรันบอท...")
    bot.run(TOKEN)