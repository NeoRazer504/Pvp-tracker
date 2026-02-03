import discord
from discord import app_commands
import sqlite3
import json
import os

TOKEN = "token"

class PvPBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()  # Registers slash commands globally
        print("Slash commands synced.")

bot = PvPBot()

@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")

@bot.event
async def on_error(event, *args, **kwargs):
    print(f"❌ Error in {event}: {args}, {kwargs}")
    conn.commit()  # Ensure data is saved on error

# Graceful shutdown handler
import atexit

def close_database():
    """Safely close database on bot shutdown."""
    try:
        # Dump players table to JSON
        try:
            c.execute("SELECT user_id, category, kills, deaths, wins, losses, winstreak, elo FROM players")
            rows = c.fetchall()
            players_list = []
            for row in rows:
                players_list.append({
                    "user_id": row[0],
                    "category": row[1],
                    "kills": row[2],
                    "deaths": row[3],
                    "wins": row[4],
                    "losses": row[5],
                    "winstreak": row[6],
                    "elo": row[7]
                })

            with open("players.json", "w", encoding="utf-8") as f:
                json.dump({"players": players_list}, f, ensure_ascii=False, indent=2)
            print(f"✅ Dumped {len(players_list)} player records to players.json")
        except Exception as e:
            print(f"⚠️ Failed to dump players to JSON: {e}")

        # Dump bans table to JSON
        try:
            c.execute("SELECT user_id, reason, banned_at FROM bans")
            ban_rows = c.fetchall()
            bans_list = []
            for row in ban_rows:
                bans_list.append({
                    "user_id": row[0],
                    "reason": row[1],
                    "banned_at": row[2]
                })

            with open("bans.json", "w", encoding="utf-8") as f:
                json.dump({"bans": bans_list}, f, ensure_ascii=False, indent=2)
            print(f"✅ Dumped {len(bans_list)} ban records to bans.json")
        except Exception as e:
            print(f"⚠️ Failed to dump bans to JSON: {e}")

        conn.commit()
        conn.close()
        print("✅ Database saved and closed.")
    except Exception as e:
        print(f"❌ Error closing database: {e}")

atexit.register(close_database)

# ---------------- DATABASE ----------------
conn = sqlite3.connect("pvp_stats.db", check_same_thread=False)
conn.isolation_level = None  # Autocommit mode
c = conn.cursor()

# --- PLAYERS TABLE ---
c.execute("""
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER,
    category TEXT,
    kills INTEGER DEFAULT 0,
    deaths INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    winstreak INTEGER DEFAULT 0,
    elo INTEGER DEFAULT 1000,
    PRIMARY KEY (user_id, category)
)
""")
conn.commit()

# --- BANS TABLE ---
c.execute("""
CREATE TABLE IF NOT EXISTS bans (
    user_id INTEGER PRIMARY KEY,
    banned_at TEXT DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
)
""")
conn.commit()

# --- HISTORY TABLE ---
c.execute("""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    action TEXT,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# --- LOAD PLAYERS FROM JSON ---
if os.path.exists("players.json"):
    try:
        with open("players.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        loaded = 0
        for p in data.get("players", []):
            try:
                uid = int(p.get("user_id"))
                cat = p.get("category", "sword")
                kills = int(p.get("kills", 0))
                deaths = int(p.get("deaths", 0))
                wins = int(p.get("wins", 0))
                losses = int(p.get("losses", 0))
                winstreak = int(p.get("winstreak", 0))
                elo = int(p.get("elo", 1000))

                c.execute(
                    "INSERT OR REPLACE INTO players (user_id, category, kills, deaths, wins, losses, winstreak, elo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (uid, cat, kills, deaths, wins, losses, winstreak, elo),
                )
                loaded += 1
            except Exception:
                continue
        conn.commit()
        print(f"✅ Loaded {loaded} player records from players.json")
    except Exception as e:
        print(f"⚠️ Failed to load players.json: {e}")

# --- LOAD BANS FROM JSON ---
if os.path.exists("bans.json"):
    try:
        with open("bans.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        loaded_bans = 0
        for b in data.get("bans", []):
            try:
                uid = int(b.get("user_id"))
                reason = b.get("reason", "No reason provided")
                banned_at = b.get("banned_at", "")

                c.execute(
                    "INSERT OR REPLACE INTO bans (user_id, reason, banned_at) VALUES (?, ?, ?)",
                    (uid, reason, banned_at),
                )
                loaded_bans += 1
            except Exception:
                continue
        conn.commit()
        print(f"✅ Loaded {loaded_bans} ban records from bans.json")
    except Exception as e:
        print(f"⚠️ Failed to load bans.json: {e}")
        
CATEGORIES = ["sword", "axe", "mace", "crystal", "uhc"]

async def category_autocomplete(interaction: discord.Interaction, current: str):
    current = current.lower()
    return [
        app_commands.Choice(name=cat.upper(), value=cat)
        for cat in CATEGORIES
        if current in cat.lower()
    ][:25]

class CategoryPager(discord.ui.View):
    def __init__(self, kind: str, target_user: discord.User | None = None, start: int = 0):
        super().__init__(timeout=300)
        self.kind = kind  # 'leaderboard' or 'stats'
        self.target_user = target_user
        self.index = start

    async def update_message(self, interaction: discord.Interaction):
        category = CATEGORIES[self.index]
        if self.kind == "leaderboard":
            c.execute("SELECT user_id, elo FROM players WHERE category = ? ORDER BY elo DESC LIMIT 10", (category,))
            top = c.fetchall()

            embed = discord.Embed(title=f"🏆 {category.upper()} Leaderboard", color=0xffd700)
            for i, (user_id, elo) in enumerate(top, start=1):
                try:
                    user = await bot.fetch_user(user_id)
                    display = user.display_name if user else f"Unknown ({user_id})"
                except:
                    display = f"Unknown ({user_id})"
                embed.add_field(name=f"#{i} {display}", value=f"Elo: {elo}", inline=False)

            await interaction.response.edit_message(embed=embed, view=self)
        else:  # stats
            target = self.target_user or interaction.user
            player = get_player(target.id, category)
            kills, deaths, wins, losses, streak, elo = player[2:]
            kd = round(kills / deaths, 2) if deaths > 0 else kills

            embed = discord.Embed(title=f"📊 {category.upper()} Stats for {target.display_name}", color=0x00ff00)
            embed.add_field(name="Kills", value=kills)
            embed.add_field(name="Deaths", value=deaths)
            embed.add_field(name="K/D", value=kd)
            embed.add_field(name="Wins", value=wins)
            embed.add_field(name="Losses", value=losses)
            embed.add_field(name="Win Streak", value=streak)
            embed.add_field(name="Elo", value=elo)

            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(CATEGORIES)
        await self.update_message(interaction)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(CATEGORIES)
        await self.update_message(interaction)

def get_player(user_id, category="sword"):
    c.execute("SELECT * FROM players WHERE user_id = ? AND category = ?", (user_id, category))
    player = c.fetchone()
    if not player:
        c.execute("INSERT INTO players (user_id, category) VALUES (?, ?)", (user_id, category))
        conn.commit()
        return get_player(user_id, category)
    return player

class DuelView(discord.ui.View):
    def __init__(self, challenger: discord.User, opponent: discord.User, category: str, kills: int):
        super().__init__(timeout=300)
        self.challenger = challenger
        self.opponent = opponent
        self.category = category
        self.kills = kills

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Only the challenged player can accept!", ephemeral=True)
            return
        
        # Create winner selection view
        winner_view = DuelResultView(self.challenger, self.opponent, self.category, self.kills)
        
        embed = discord.Embed(title="⚔️ Duel In Progress", color=0xff6600)
        embed.add_field(name="Challenger", value=self.challenger.mention)
        embed.add_field(name="Opponent", value=self.opponent.mention)
        embed.add_field(name="Category", value=self.category.upper())
        embed.set_footer(text="Who won the duel?")
        
        await interaction.response.send_message(embed=embed, view=winner_view)
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Only the challenged player can decline!", ephemeral=True)
            return
        
        await interaction.response.send_message(f"❌ {self.opponent.mention} declined the duel from {self.challenger.mention}!")
        self.stop()

class DuelResultView(discord.ui.View):
    def __init__(self, challenger: discord.User, opponent: discord.User, category: str, kills: int):
        super().__init__(timeout=300)
        self.challenger = challenger
        self.opponent = opponent
        self.category = category
        self.kills = kills

    @discord.ui.button(label=f"Challenger Won", style=discord.ButtonStyle.blurple)
    async def challenger_won(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Challenger won, opponent lost
        winner = self.challenger
        loser = self.opponent
        
        winner_data = get_player(winner.id, self.category)
        loser_data = get_player(loser.id, self.category)
        
        winner_elo = winner_data[7]
        loser_elo = loser_data[7]
        
        winner_gain, loser_loss = calculate_elo_change(winner_elo, loser_elo, self.kills)
        
        c.execute(
            "UPDATE players SET kills = MAX(0, kills + ?), wins = wins + 1, winstreak = winstreak + 1, elo = MAX(0, elo + ?) WHERE user_id = ? AND category = ?",
            (self.kills, winner_gain, winner.id, self.category)
        )
        c.execute(
            "UPDATE players SET deaths = MAX(0, deaths + ?), losses = losses + 1, winstreak = 0, elo = MAX(0, elo + ?) WHERE user_id = ? AND category = ?",
            (self.kills, loser_loss, loser.id, self.category)
        )
        conn.commit()
        
        log_history(
            winner.id,
            self.category,
            "duel_win",
            f"{winner.display_name} defeated {loser.display_name} (kills: {self.kills}, ΔELO: +{winner_gain}/{loser_loss})"
        )

        await interaction.response.send_message(f"⚔️ Duel finished! {winner.mention} defeated {loser.mention} in **{self.category}**! (+{winner_gain} / {loser_loss} ELO)")
        self.stop()

    @discord.ui.button(label=f"Opponent Won", style=discord.ButtonStyle.blurple)
    async def opponent_won(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Opponent won, challenger lost
        winner = self.opponent
        loser = self.challenger
        
        winner_data = get_player(winner.id, self.category)
        loser_data = get_player(loser.id, self.category)
        
        winner_elo = winner_data[7]
        loser_elo = loser_data[7]
        
        winner_gain, loser_loss = calculate_elo_change(winner_elo, loser_elo, self.kills)
        
        c.execute(
            "UPDATE players SET kills = MAX(0, kills + ?), wins = wins + 1, winstreak = winstreak + 1, elo = MAX(0, elo + ?) WHERE user_id = ? AND category = ?",
            (self.kills, winner_gain, winner.id, self.category)
        )
        c.execute(
            "UPDATE players SET deaths = MAX(0, deaths + ?), losses = losses + 1, winstreak = 0, elo = MAX(0, elo + ?) WHERE user_id = ? AND category = ?",
            (self.kills, loser_loss, loser.id, self.category)
        )
        conn.commit()
        
        log_history(
            winner.id,
            self.category,
            "duel_win",
            f"{winner.display_name} defeated {loser.display_name} (kills: {self.kills}, ΔELO: +{winner_gain}/{loser_loss})"
        )

        await interaction.response.send_message(f"⚔️ Duel finished! {winner.mention} defeated {loser.mention} in **{self.category}**! (+{winner_gain} / {loser_loss} ELO)")
        self.stop()

def calculate_elo_change(winner_elo: int, loser_elo: int, kill_difference: int = 1) -> tuple[int, int]:
    """
    New ELO system:
    - Base K = 24
    - Scales with kill difference (margin of victory)
    - Considers rating difference via expected score
    - Winner always gains ELO
    - Loser always loses ELO
    - ELO cannot go below 0 (handled later in SQL)
    """
    if kill_difference < 1:
        kill_difference = 1

    # Expected score for winner
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))

    # Margin multiplier (up to ~2x for big wins)
    margin_multiplier = 1 + min(kill_difference, 5) * 0.15

    base_k = 24
    raw_change = base_k * margin_multiplier * (1 - expected_winner)

    winner_gain = int(round(raw_change))
    if winner_gain < 5:
        winner_gain = 5  # minimum gain

    loser_loss = -winner_gain
    return winner_gain, loser_loss

def is_banned(user_id: int) -> bool:
    """Check if a user is banned."""
    c.execute("SELECT 1 FROM bans WHERE user_id = ?", (user_id,))
    return c.fetchone() is not None

# --- HISTORY LOGGER ---
def log_history(user_id: int | None, category: str | None, action: str, details: str):
    c.execute(
        "INSERT INTO history (user_id, category, action, details) VALUES (?, ?, ?, ?)",
        (user_id, category, action, details),
    )
    conn.commit()

# ---------------- SLASH COMMANDS ----------------

@bot.tree.command(name="register", description="Register yourself or another user")
@app_commands.default_permissions(administrator=True)
async def register(interaction: discord.Interaction, user: discord.User = None):
    target_user = user or interaction.user
    user_id = target_user.id
    
    # Check if banned
    if is_banned(user_id):
        await interaction.response.send_message(f"❌ {target_user.mention} is banned and cannot register!", ephemeral=True)
        return
    
    # Check if user exists in any category
    c.execute("SELECT COUNT(*) FROM players WHERE user_id = ?", (user_id,))
    count = c.fetchone()[0]
    
    if count > 0:
        await interaction.response.send_message(f"❌ {target_user.mention} is already registered!", ephemeral=True)
    else:
        # Create entries for all categories
        for cat in CATEGORIES:
            c.execute("INSERT INTO players (user_id, category) VALUES (?, ?)", (user_id, cat))
        conn.commit()
        await interaction.response.send_message(f"✅ {target_user.mention} registered for all categories!")

@bot.tree.command(name="remove", description="Remove a player from the database")
@app_commands.default_permissions(administrator=True)
async def remove(interaction: discord.Interaction, user: discord.User = None):
    target_id = user.id if user else interaction.user.id
    c.execute("SELECT * FROM players WHERE user_id = ?", (target_id,))
    existing = c.fetchone()
    if not existing:
        target_name = user.mention if user else "You"
        await interaction.response.send_message(f"❌ {target_name} is not registered!", ephemeral=True)
    else:
        c.execute("DELETE FROM players WHERE user_id = ?", (target_id,))
        conn.commit()
        target_name = user.mention if user else interaction.user.mention
        await interaction.response.send_message(f"🗑️ {target_name} removed from all categories!")

@bot.tree.command(name="ban", description="Ban a player")
@app_commands.default_permissions(administrator=True)
async def ban(interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided"):
    if is_banned(user.id):
        await interaction.response.send_message(f"❌ {user.mention} is already banned!", ephemeral=True)
        return
    
    c.execute("INSERT INTO bans (user_id, reason) VALUES (?, ?)", (user.id, reason))
    conn.commit()
    await interaction.response.send_message(f"🔒 {user.mention} has been banned! Reason: {reason}")

@bot.tree.command(name="unban", description="Unban a player")
@app_commands.default_permissions(administrator=True)
async def unban(interaction: discord.Interaction, user: discord.User):
    if not is_banned(user.id):
        await interaction.response.send_message(f"❌ {user.mention} is not banned!", ephemeral=True)
        return
    
    c.execute("DELETE FROM bans WHERE user_id = ?", (user.id,))
    conn.commit()
    await interaction.response.send_message(f"🔓 {user.mention} has been unbanned!")

@bot.tree.command(name="banlist", description="View all banned players")
@app_commands.default_permissions(administrator=True)
async def banlist(interaction: discord.Interaction):
    c.execute("SELECT user_id, reason, banned_at FROM bans ORDER BY banned_at DESC")
    bans = c.fetchall()
    
    if not bans:
        await interaction.response.send_message("✅ No banned players!", ephemeral=True)
        return
    
    embed = discord.Embed(title="🔒 Banned Players", color=0xff0000)
    for user_id, reason, banned_at in bans:
        embed.add_field(name=f"ID: {user_id}", value=f"Reason: {reason}\nBanned: {banned_at}", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="edit", description="Edit player stats")
@app_commands.default_permissions(administrator=True)
async def edit(interaction: discord.Interaction, user: discord.User, category: str = "sword", kills: int = None, deaths: int = None, wins: int = None, losses: int = None, elo: int = None, winstreak: int = None):
    if category not in CATEGORIES:
        await interaction.response.send_message(f"❌ Invalid category! Choose from: {', '.join(CATEGORIES)}", ephemeral=True)
        return
    
    c.execute("SELECT * FROM players WHERE user_id = ? AND category = ?", (user.id, category))
    player = c.fetchone()
    if not player:
        await interaction.response.send_message(f"❌ {user.mention} has no stats in **{category}**!", ephemeral=True)
        return
    
    updates = []
    params = []
    if kills is not None:
        updates.append("kills = ?")
        params.append(kills)
    if deaths is not None:
        updates.append("deaths = ?")
        params.append(deaths)
    if wins is not None:
        updates.append("wins = ?")
        params.append(wins)
    if losses is not None:
        updates.append("losses = ?")
        params.append(losses)
    if elo is not None:
        if elo < 0:
            elo = 0
        updates.append("elo = ?")
        params.append(elo)
    if winstreak is not None:
        updates.append("winstreak = ?")
        params.append(winstreak)
    
    if not updates:
        await interaction.response.send_message(f"❌ No stats provided to update!", ephemeral=True)
        return
    
    params.append(user.id)
    params.append(category)
    query = "UPDATE players SET " + ", ".join(updates) + " WHERE user_id = ? AND category = ?"
    c.execute(query, params)
    conn.commit()

    log_history(
        user.id,
        category,
        "admin_edit",
        f"Admin {interaction.user.display_name} edited stats for {user.display_name}"
    )
    
    await interaction.response.send_message(f"✏️ Updated {user.mention}'s **{category}** stats!")

@bot.tree.command(name="report", description="Report a PvP match result")
async def report(interaction: discord.Interaction, winner: discord.User, loser: discord.User, category: str = "sword", kills: int = 1):
    # Check if user is the winner or an admin
    is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
    is_winner = interaction.user.id == winner.id
    
    if not (is_winner or is_admin):
        await interaction.response.send_message(f"❌ Only {winner.mention} or administrators can report this match!", ephemeral=True)
        return
    
    # Check if either player is banned
    if is_banned(winner.id):
        await interaction.response.send_message(f"❌ {winner.mention} is banned and cannot report matches!", ephemeral=True)
        return
    if is_banned(loser.id):
        await interaction.response.send_message(f"❌ {loser.mention} is banned and cannot report matches!", ephemeral=True)
        return
    
    if category not in CATEGORIES:
        await interaction.response.send_message(f"❌ Invalid category! Choose from: {', '.join(CATEGORIES)}", ephemeral=True)
        return
    
    winner_data = get_player(winner.id, category)
    loser_data = get_player(loser.id, category)

    # row layout: user_id, category, kills, deaths, wins, losses, winstreak, elo
    winner_elo = winner_data[7]
    loser_elo = loser_data[7]
    
    winner_gain, loser_loss = calculate_elo_change(winner_elo, loser_elo, kills)
    
    c.execute(
    "UPDATE players SET kills = MAX(0, kills + ?), wins = wins + 1, winstreak = winstreak + 1, elo = MAX(0, elo + ?) WHERE user_id = ? AND category = ?",
    (kills, winner_gain, winner.id, category)
    )
    c.execute(
        "UPDATE players SET deaths = MAX(0, deaths + ?), losses = losses + 1, winstreak = 0, elo = MAX(0, elo + ?) WHERE user_id = ? AND category = ?",
        (kills, loser_loss, loser.id, category)
    )
    conn.commit()

    log_history(
        winner.id,
        category,
        "match_report",
        f"{winner.display_name} defeated {loser.display_name} (kills: {kills}, ΔELO: +{winner_gain}/{loser_loss})"
    )

    await interaction.response.send_message(f"⚔️ {winner.mention} defeated {loser.mention} in **{category}**! (+{winner_gain} / {loser_loss} ELO)")

@bot.tree.command(name="duel", description="Challenge a player to a duel")
async def duel(interaction: discord.Interaction, opponent: discord.User, category: str = "sword", kills: int = 1):
    challenger = interaction.user
    
    # Check if either player is banned
    if is_banned(challenger.id):
        await interaction.response.send_message(f"❌ You are banned and cannot duel!", ephemeral=True)
        return
    if is_banned(opponent.id):
        await interaction.response.send_message(f"❌ {opponent.mention} is banned and cannot duel!", ephemeral=True)
        return
    
    if category not in CATEGORIES:
        await interaction.response.send_message(f"❌ Invalid category! Choose from: {', '.join(CATEGORIES)}", ephemeral=True)
        return
    
    if challenger.id == opponent.id:
        await interaction.response.send_message(f"❌ You cannot duel yourself!", ephemeral=True)
        return
    
    # Create duel view
    view = DuelView(challenger, opponent, category, kills)
    
    # Send notification to opponent
    embed = discord.Embed(title="⚔️ Duel Challenge", color=0xff6600)
    embed.add_field(name="Challenger", value=challenger.mention)
    embed.add_field(name="Category", value=category.upper())
    embed.add_field(name="Kill Difference", value=kills)
    embed.set_footer(text="You have 5 minutes to accept or decline")
    
    await interaction.response.send_message(f"{opponent.mention} has been challenged to a duel!", ephemeral=True)
    await opponent.send(embed=embed, view=view)

@bot.tree.command(name="stats", description="View player stats")
async def stats(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    category: str | None = None,
):
    target_user = user or interaction.user

    # -------------------------
    # OVERALL STATS
    # -------------------------
    if category is None:
        c.execute("""
            SELECT
                SUM(kills),
                SUM(deaths),
                SUM(wins),
                SUM(losses),
                MAX(winstreak),
                AVG(elo)
            FROM players
            WHERE user_id = ?
        """, (target_user.id,))
        row = c.fetchone()

        if not row or row[0] is None:
            await interaction.response.send_message(
                f"❌ {target_user.mention} has no stats yet!",
                ephemeral=True,
            )
            return

        kills, deaths, wins, losses, streak, avg_elo = row
        kd = round(kills / deaths, 2) if deaths and deaths > 0 else kills
        elo_display = int(round(avg_elo)) if avg_elo is not None else 0

        embed = discord.Embed(
            title=f"📊 Overall Stats for {target_user.display_name}",
            color=0x00ff00,
        )
        embed.add_field(name="Kills", value=kills)
        embed.add_field(name="Deaths", value=deaths)
        embed.add_field(name="K/D", value=kd)
        embed.add_field(name="Wins", value=wins)
        embed.add_field(name="Losses", value=losses)
        embed.add_field(name="Best Win Streak", value=streak)
        embed.add_field(name="Average Elo", value=elo_display)

        await interaction.response.send_message(embed=embed)
        return

    # -------------------------
    # CATEGORY STATS
    # -------------------------
    if category not in CATEGORIES:
        await interaction.response.send_message(
            f"❌ Invalid category! Choose from: {', '.join(CATEGORIES)}",
            ephemeral=True,
        )
        return

    player = get_player(target_user.id, category)
    kills, deaths, wins, losses, streak, elo = player[2:]
    kd = round(kills / deaths, 2) if deaths > 0 else kills

    embed = discord.Embed(
        title=f"📊 {category.upper()} Stats for {target_user.display_name}",
        color=0x00ff00,
    )
    embed.add_field(name="Kills", value=kills)
    embed.add_field(name="Deaths", value=deaths)
    embed.add_field(name="K/D", value=kd)
    embed.add_field(name="Wins", value=wins)
    embed.add_field(name="Losses", value=losses)
    embed.add_field(name="Win Streak", value=streak)
    embed.add_field(name="Elo", value=elo)

    idx = CATEGORIES.index(category)
    view = CategoryPager("stats", target_user=target_user, start=idx)

    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="leaderboard", description="Top PvP players")
async def leaderboard(interaction: discord.Interaction, category: str | None = None):
    # -------------------------
    # OVERALL LEADERBOARD
    # -------------------------
    if category is None:
        c.execute("""
            SELECT user_id, AVG(elo) AS avg_elo
            FROM players
            GROUP BY user_id
            ORDER BY avg_elo DESC
            LIMIT 10
        """)
        top = c.fetchall()

        embed = discord.Embed(title="🏆 Overall Leaderboard", color=0xffd700)

        for i, (user_id, avg_elo) in enumerate(top, start=1):
            try:
                user = await bot.fetch_user(user_id)
                display = user.display_name if user else f"Unknown ({user_id})"
            except:
                display = f"Unknown ({user_id})"

            embed.add_field(
                name=f"#{i} {display}",
                value=f"Average Elo: {int(round(avg_elo))}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)
        return

    # -------------------------
    # CATEGORY LEADERBOARD
    # -------------------------
    if category not in CATEGORIES:
        await interaction.response.send_message(
            f"❌ Invalid category! Choose from: {', '.join(CATEGORIES)}",
            ephemeral=True
        )
        return

    c.execute(
        "SELECT user_id, elo FROM players WHERE category = ? ORDER BY elo DESC LIMIT 10",
        (category,)
    )
    top = c.fetchall()

    embed = discord.Embed(title=f"🏆 {category.upper()} Leaderboard", color=0xffd700)

    for i, (user_id, elo) in enumerate(top, start=1):
        try:
            user = await bot.fetch_user(user_id)
            display = user.display_name if user else f"Unknown ({user_id})"
        except:
            display = f"Unknown ({user_id})"

        embed.add_field(
            name=f"#{i} {display}",
            value=f"Elo: {elo}",
            inline=False
        )

    idx = CATEGORIES.index(category)
    view = CategoryPager("leaderboard", start=idx)

    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="mace", description="Top 10 Mace players")
async def mace_lb(interaction: discord.Interaction):
    c.execute("SELECT user_id, elo FROM players WHERE category = ? ORDER BY elo DESC LIMIT 10", ("mace",))
    top = c.fetchall()

    embed = discord.Embed(title="🏆 Mace Leaderboard", color=0xffd700)
    for i, (user_id, elo) in enumerate(top, start=1):
        try:
            user = await bot.fetch_user(user_id)
            display = user.display_name if user else f"Unknown ({user_id})"
        except:
            display = f"Unknown ({user_id})"
        embed.add_field(name=f"#{i} {display}", value=f"Elo: {elo}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="crystal", description="Top 10 Crystal players")
async def crystal_lb(interaction: discord.Interaction):
    c.execute("SELECT user_id, elo FROM players WHERE category = ? ORDER BY elo DESC LIMIT 10", ("crystal",))
    top = c.fetchall()

    embed = discord.Embed(title="🏆 Crystal Leaderboard", color=0xffd700)
    for i, (user_id, elo) in enumerate(top, start=1):
        try:
            user = await bot.fetch_user(user_id)
            display = user.display_name if user else f"Unknown ({user_id})"
        except:
            display = f"Unknown ({user_id})"
        embed.add_field(name=f"#{i} {display}", value=f"Elo: {elo}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="uhc", description="Top 10 UHC players")
async def uhc_lb(interaction: discord.Interaction):
    c.execute("SELECT user_id, elo FROM players WHERE category = ? ORDER BY elo DESC LIMIT 10", ("uhc",))
    top = c.fetchall()

    embed = discord.Embed(title="🏆 UHC Leaderboard", color=0xffd700)
    for i, (user_id, elo) in enumerate(top, start=1):
        try:
            user = await bot.fetch_user(user_id)
            if user.bot:
                embed.add_field(name=f"#{i} {user.display_name}", value=f"Elo: {elo}", inline=False)
        except:
            pass
    await interaction.response.send_message(embed=embed)
@app_commands.default_permissions(administrator=True)
async def wipe(interaction: discord.Interaction):
    try:
        c.execute("SELECT DISTINCT user_id FROM players")
        user_ids = c.fetchall()
        
        deleted = 0
        for (user_id,) in user_ids:
            try:
                user = await bot.fetch_user(user_id)
                if not user.bot:  # Delete non-bot users
                    c.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
                    deleted += 1
            except:
                # User not found, delete anyway
                c.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
                deleted += 1
        
        conn.commit()
        await interaction.response.send_message(f"✅ Wiped {deleted} non-bot players from database!")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="reset", description="Reset a player's stats in a category")
@app_commands.default_permissions(administrator=True)
async def reset(interaction: discord.Interaction, user: discord.User, category: str = "sword"):
    if category not in CATEGORIES:
        await interaction.response.send_message(f"❌ Invalid category! Choose from: {', '.join(CATEGORIES)}", ephemeral=True)
        return
    
    c.execute("SELECT * FROM players WHERE user_id = ? AND category = ?", (user.id, category))
    player = c.fetchone()
    if not player:
        await interaction.response.send_message(f"❌ {user.mention} has no stats in **{category}**!", ephemeral=True)
        return
    
    c.execute(
        "UPDATE players SET kills = 0, deaths = 0, wins = 0, losses = 0, winstreak = 0, elo = 1000 WHERE user_id = ? AND category = ?",
        (user.id, category)
    )
    conn.commit()

    log_history(
        user.id,
        category,
        "reset",
        f"Admin {interaction.user.display_name} reset stats for {user.display_name}"
    )

    await interaction.response.send_message(f"🔄 Reset {user.mention}'s **{category}** stats to default!")

@bot.tree.command(name="history", description="Show recent PvP history (reports, edits, duels, etc.)")
async def history(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    category: str | None = None
):
    params = []
    query = "SELECT user_id, category, action, details, created_at FROM history WHERE 1=1"

    # Filter by user
    if user is not None:
        query += " AND user_id = ?"
        params.append(user.id)

    # Filter by category
    if category is not None:
        query += " AND category = ?"
        params.append(category)

    # Sort newest → oldest
    query += " ORDER BY created_at DESC LIMIT 20"

    c.execute(query, params)
    rows = c.fetchall()

    if not rows:
        await interaction.response.send_message("📭 No history found for that filter.", ephemeral=True)
        return

    # Title building
    title = "📜 Recent History"
    if user:
        title += f" for {user.display_name}"
    if category:
        title += f" in {category.upper()}"

    embed = discord.Embed(title=title, color=0x7289da)

    for user_id, cat, action, details, created_at in rows:
        cat_label = cat.upper() if cat else "OVERALL"
        embed.add_field(
            name=f"[{created_at}] {action.upper()} — {cat_label}",
            value=f"👤 User: <@{user_id}>\n📝 {details}",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

@stats.autocomplete("category")
@leaderboard.autocomplete("category")
@history.autocomplete("category")
@report.autocomplete("category")
@duel.autocomplete("category")
@edit.autocomplete("category")
@reset.autocomplete("category")
async def _category_autocomplete(interaction: discord.Interaction, current: str):
    return await category_autocomplete(interaction, current)

bot.run(TOKEN)
