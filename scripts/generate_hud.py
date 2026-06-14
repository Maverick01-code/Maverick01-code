import os
import json
import urllib.request
import urllib.error
import datetime
import random

# Default username and target output file
USERNAME = "Maverick01-code"
OUTPUT_FILE = "dist/cv-contribution-hud.svg"

# GraphQL Query to fetch user contributions
GRAPHQL_QUERY = """
query($username: String!) {
  user(login: $username) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
            weekday
          }
        }
      }
    }
  }
}
"""

def fetch_contributions(username, token=None):
    """Fetches contributions using GitHub GraphQL API, with fallback to mock data."""
    if not token:
        print("Warning: GITHUB_TOKEN not provided. Generating mock data for local testing.")
        return generate_mock_data()
        
    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Maverick01-code-CV-HUD-Visualizer"
    }
    data = {
        "query": GRAPHQL_QUERY,
        "variables": {"username": username}
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if "errors" in res_data:
                print(f"GraphQL Errors: {res_data['errors']}")
                print("Falling back to mock data.")
                return generate_mock_data()
            return res_data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    except Exception as e:
        print(f"Failed to fetch from GitHub API: {e}")
        print("Falling back to mock data.")
        return generate_mock_data()

def generate_mock_data():
    """Generates realistic mock contribution data for testing and fallback."""
    print("Generating fallback mock contribution data...")
    today = datetime.date.today()
    # Find the Sunday of the week 52 weeks ago
    start_date = today - datetime.timedelta(weeks=52)
    start_date -= datetime.timedelta(days=(start_date.weekday() + 1) % 7) # Adjust to Sunday
    
    weeks = []
    current_date = start_date
    
    # We will seed random to make mock data semi-consistent, but with nice clusters
    random.seed(42)
    
    # Generate some cluster centers (week_idx, day_idx)
    centers = [(random.randint(5, 48), random.randint(1, 5)) for _ in range(15)]
    
    for w in range(53):
        days = []
        for d in range(7):
            # Base probability of commit
            dist_to_center = min(abs(w - cw) + abs(d - cd) for cw, cd in centers)
            
            if dist_to_center == 0:
                count = random.randint(8, 12)
            elif dist_to_center == 1:
                count = random.randint(4, 7)
            elif dist_to_center == 2:
                count = random.randint(1, 3)
            else:
                # Background noise (10% chance of 1 commit)
                count = 1 if random.random() < 0.1 else 0
                
            days.append({
                "contributionCount": count,
                "date": current_date.isoformat(),
                "weekday": d
            })
            current_date += datetime.timedelta(days=1)
        weeks.append({"contributionDays": days})
        
    return {
        "totalContributions": sum(d["contributionCount"] for w in weeks for d in w["contributionDays"]),
        "weeks": weeks
    }

def run_ccl(grid, rows, cols):
    """
    Connected Component Labeling using 8-connectivity.
    Finds groups of contiguous cells with commits > 0.
    """
    visited = [[False for _ in range(cols)] for _ in range(rows)]
    clusters = []
    
    def get_neighbors(r, c):
        neighbors = []
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    neighbors.append((nr, nc))
        return neighbors

    for r in range(rows):
        for c in range(cols):
            if grid[r][c] > 0 and not visited[r][c]:
                cluster = []
                queue = [(r, c)]
                visited[r][c] = True
                while queue:
                    curr_r, curr_c = queue.pop(0)
                    cluster.append((curr_r, curr_c))
                    for nr, nc in get_neighbors(curr_r, curr_c):
                        if grid[nr][nc] > 0 and not visited[nr][nc]:
                            visited[nr][nc] = True
                            queue.append((nr, nc))
                clusters.append(cluster)
    return clusters

def generate_svg(calendar_data):
    """Generates the animated CV HUD SVG from calendar data."""
    weeks = calendar_data["weeks"]
    total_commits = calendar_data["totalContributions"]
    
    cols = len(weeks)
    rows = 7
    
    # Create 2D grid
    grid = [[0 for _ in range(cols)] for _ in range(rows)]
    for w_idx, week in enumerate(weeks):
        for day in week["contributionDays"]:
            r = day["weekday"]
            grid[r][w_idx] = day["contributionCount"]
            
    # Run clustering
    clusters = run_ccl(grid, rows, cols)
    
    # Process clusters into bounding boxes
    detected_boxes = []
    box_id = 1
    for cluster in clusters:
        size = len(cluster)
        max_commits = max(grid[r][c] for r, c in cluster)
        sum_commits = sum(grid[r][c] for r, c in cluster)
        
        min_r = min(r for r, c in cluster)
        max_r = max(r for r, c in cluster)
        min_c = min(c for r, c in cluster)
        max_c = max(c for r, c in cluster)
        
        # Bounding box width and height in grid cells
        w_cells = max_c - min_c + 1
        h_cells = max_r - min_r + 1
        
        # Determine class based on aspect ratio and commit density
        if size >= 3:
            if w_cells > h_cells * 1.5:
                cls = "DEV_STREAK"
            else:
                cls = "COMMIT_CLUSTER"
            
            # Deterministic pseudo-confidence score
            # Seed the random number generator using cluster contents so it's stable across builds
            state_seed = sum_commits + min_r * 7 + min_c * 53
            rng = random.Random(state_seed)
            conf = min(99.8, 88.0 + (sum_commits / size) * 1.5 + rng.uniform(-2.0, 2.0))
            
            detected_boxes.append({
                "id": box_id,
                "min_r": min_r, "max_r": max_r,
                "min_c": min_c, "max_c": max_c,
                "class": cls,
                "conf": round(conf, 1),
                "total": sum_commits,
                "size": size
            })
            box_id += 1
            
        elif size == 1 and max_commits >= 5:
            # Single day with massive activity
            state_seed = max_commits + min_r * 11 + min_c * 31
            rng = random.Random(state_seed)
            conf = min(99.5, 92.0 + max_commits + rng.uniform(-1.0, 1.0))
            detected_boxes.append({
                "id": box_id,
                "min_r": min_r, "max_r": max_r,
                "min_c": min_c, "max_c": max_c,
                "class": "PEAK_BURST",
                "conf": round(conf, 1),
                "total": sum_commits,
                "size": size
            })
            box_id += 1

    # Base layouts and positioning
    # Left margin is 130 to allow space for technical sidebar HUD
    GRID_X0 = 140
    GRID_Y0 = 85
    CELL_SIZE = 10
    CELL_GAP = 4
    STEP = CELL_SIZE + CELL_GAP # 14px
    
    grid_width = cols * STEP - CELL_GAP
    grid_height = rows * STEP - CELL_GAP
    
    svg_width = GRID_X0 + grid_width + 40
    svg_height = GRID_Y0 + grid_height + 70
    
    # Render cell squares
    squares_svg = []
    
    # Custom futuristic color palette mapping
    # 0 commits: `#121620` (dark blue-gray)
    # 1-2 commits: `#0052cc` -> `#00f0ff` (glowing cyan transition)
    # 3-5 commits: `#a300cc` -> `#bd00ff` (glowing purple)
    # 6-8 commits: `#e60073` -> `#ff007a` (glowing magenta)
    # 9+ commits: `#ffffff` (glowing white)
    def get_color_and_glow(count):
        if count == 0:
            return "#121620", "none", 0.4
        elif count <= 2:
            return "#00f0ff", "url(#cyan-glow)", 0.8
        elif count <= 5:
            return "#bd00ff", "url(#purple-glow)", 0.9
        elif count <= 8:
            return "#ff007a", "url(#pink-glow)", 1.0
        else:
            return "#ffffff", "url(#white-glow)", 1.0

    for c in range(cols):
        for r in range(rows):
            count = grid[r][c]
            color, filter_glow, opacity = get_color_and_glow(count)
            x = GRID_X0 + c * STEP
            y = GRID_Y0 + r * STEP
            
            # Subtle glow filter only applied to active commit squares
            filter_attr = f' filter="{filter_glow}"' if filter_glow != "none" else ""
            squares_svg.append(
                f'      <rect x="{x}" y="{y}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="2" ry="2" fill="{color}" opacity="{opacity}"{filter_attr} />'
            )
            
    # Render bounding boxes
    boxes_svg = []
    box_colors = {
        "DEV_STREAK": "#00f0ff",       # Cyan
        "COMMIT_CLUSTER": "#39ff14",   # Neon Green
        "PEAK_BURST": "#ff007a"        # Neon Pink
    }
    
    for box in detected_boxes:
        color = box_colors.get(box["class"], "#00f0ff")
        bx = GRID_X0 + box["min_c"] * STEP - 3
        by = GRID_Y0 + box["min_r"] * STEP - 3
        bw = (box["max_c"] - box["min_c"]) * STEP + CELL_SIZE + 6
        bh = (box["max_r"] - box["min_r"]) * STEP + CELL_SIZE + 6
        
        # Bounding box animation: subtle pulsing pulse class
        # Add labels
        label_text = f"{box['class']} {box['conf']}%"
        label_w = len(label_text) * 5.8 + 8
        
        # Generate SVG elements for the bounding box
        box_el = f"""
      <g class="hud-bbox" style="--bbox-color: {color};">
        <!-- Main box outline -->
        <rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="none" stroke="{color}" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.85" />
        
        <!-- Corner brackets for target locking -->
        <path d="M {bx}, {by+6} L {bx}, {by} L {bx+6}, {by}" fill="none" stroke="{color}" stroke-width="2" />
        <path d="M {bx+bw-6}, {by} L {bx+bw}, {by} L {bx+bw}, {by+6}" fill="none" stroke="{color}" stroke-width="2" />
        <path d="M {bx}, {by+bh-6} L {bx}, {by+bh} L {bx+6}, {by+bh}" fill="none" stroke="{color}" stroke-width="2" />
        <path d="M {bx+bw-6}, {by+bh} L {bx+bw}, {by+bh} L {bx+bw}, {by+bh-6}" fill="none" stroke="{color}" stroke-width="2" />
        
        <!-- Class Tag Label -->
        <rect x="{bx}" y="{by-13}" width="{label_w}" height="13" fill="{color}" opacity="0.9" />
        <text x="{bx+4}" y="{by-3}" fill="#080c14" font-family="'Share Tech Mono', monospace" font-size="9" font-weight="bold">{label_text}</text>
      </g>"""
        boxes_svg.append(box_el)

    # Render months headers
    month_headers = []
    # Standard months calculation
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    prev_month = -1
    for c in range(cols):
        # Find date of first day of the week
        first_day_date_str = weeks[c]["contributionDays"][0]["date"]
        try:
            dt = datetime.datetime.strptime(first_day_date_str, "%Y-%m-%d")
            m = dt.month - 1
            if m != prev_month and c > 1 and c < cols - 2:
                # Add month label
                mx = GRID_X0 + c * STEP
                month_headers.append(
                    f'      <text x="{mx}" y="{GRID_Y0 - 15}" fill="#58a6ff" font-family="\'Share Tech Mono\', monospace" font-size="10">{month_names[m]}</text>'
                )
                prev_month = m
        except Exception:
            pass

    # Dynamic log output lines for console
    logs = [
        f"&gt;&gt; FRAME: [53x7] | TARGET: {USERNAME}",
        f"&gt;&gt; CCL_ENGINE: DETECTED {len(clusters)} RAW CLUSTERS",
        f"&gt;&gt; YOLOv8_COMMIT: STRETCHING {len(detected_boxes)} ROIs",
        f"&gt;&gt; SCANNING COMPLETED SUCCESSFULLY."
    ]
    
    log_elements = []
    for idx, log in enumerate(logs):
        log_elements.append(
            f'<text x="140" y="{GRID_Y0 + grid_height + 25 + idx*11}" fill="#58a6ff" font-family="\'Share Tech Mono\', monospace" font-size="9" opacity="0.7">{log}</text>'
        )

    # Join lists before formatting to avoid backslashes inside f-string expressions (for Python < 3.12 compatibility)
    months_joined = "\n".join(month_headers)
    squares_joined = "\n".join(squares_svg)
    boxes_joined = "\n".join(boxes_svg)
    logs_joined = "\n".join(log_elements)

    # Complete SVG contents
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="{svg_width}" height="{svg_height}">
  <defs>
    <!-- Google Font Import -->
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&amp;display=swap');
      
      /* Micro-animations */
      @keyframes blink {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.3; }}
      }}
      
      @keyframes scan {{
        0% {{ transform: translateX(0); opacity: 0.8; }}
        50% {{ opacity: 1; }}
        100% {{ transform: translateX({grid_width}px); opacity: 0.8; }}
      }}
      
      @keyframes pulse-box {{
        0%, 100% {{ transform: scale(1); opacity: 0.95; }}
        50% {{ transform: scale(1.01); opacity: 0.8; }}
      }}
      
      .blinking {{
        animation: blink 2s infinite;
      }}
      
      .laser-scanner {{
        animation: scan 8s linear infinite alternate;
      }}
      
      .hud-bbox {{
        transform-origin: center;
        /* Subtle glow hover effect */
        transition: all 0.3s ease;
      }}
      
      .hud-bbox:hover {{
        filter: drop-shadow(0 0 4px var(--bbox-color));
        opacity: 1 !important;
      }}
      
      .interactive-grid-cell:hover {{
        transform: scale(1.2);
        stroke: #ffffff;
        stroke-width: 1;
        z-index: 100;
      }}
    </style>
    
    <!-- Neon glows -->
    <filter id="cyan-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.5" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    
    <filter id="purple-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.5" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    
    <filter id="pink-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.8" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    
    <filter id="white-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2.2" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    
    <!-- Radar gradient sweep tail -->
    <linearGradient id="laser-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.0"/>
      <stop offset="85%" stop-color="#00f0ff" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#00f0ff" stop-opacity="0.75"/>
    </linearGradient>
  </defs>

  <!-- Dark cybernetic background -->
  <rect width="{svg_width}" height="{svg_height}" fill="#080c14" rx="8" stroke="#1f2937" stroke-width="1" />
  
  <!-- Outer technical hud frame -->
  <rect x="8" y="8" width="{svg_width-16}" height="{svg_height-16}" fill="none" stroke="#00f0ff" stroke-width="0.8" opacity="0.15" />
  <rect x="12" y="12" width="{svg_width-24}" height="{svg_height-24}" fill="none" stroke="#00f0ff" stroke-width="0.5" opacity="0.08" />

  <!-- Diagonal tech corner tick marks -->
  <path d="M 8,24 L 24,8" stroke="#00f0ff" stroke-width="1" opacity="0.4" />
  <path d="M {svg_width-8},24 L {svg_width-24},8" stroke="#00f0ff" stroke-width="1" opacity="0.4" />
  <path d="M 8,{svg_height-24} L 24,{svg_height-8}" stroke="#00f0ff" stroke-width="1" opacity="0.4" />
  <path d="M {svg_width-8},{svg_height-24} L {svg_width-24},{svg_height-8}" stroke="#00f0ff" stroke-width="1" opacity="0.4" />

  <!-- Telemetry/Header panel -->
  <g transform="translate(25, 25)">
    <!-- Tech brackets for title -->
    <path d="M 0,16 L 0,0 L 20,0" fill="none" stroke="#00f0ff" stroke-width="1.5" />
    <text x="8" y="15" fill="#00f0ff" font-family="'Share Tech Mono', monospace" font-size="14" font-weight="bold">TARGET_DETECTION_HUD</text>
    <text x="8" y="28" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="9" opacity="0.6">SENSOR_ARRAY: COMMIT_LOGS | CAM_01</text>
  </g>
  
  <!-- Blinking status light top-right -->
  <g transform="translate({svg_width - 150}, 25)">
    <circle cx="10" cy="10" r="4" fill="#00ff66" class="blinking" />
    <text x="20" y="13" fill="#00ff66" font-family="'Share Tech Mono', monospace" font-size="10" font-weight="bold">SYS_ACTIVE</text>
    <text x="20" y="25" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="9" opacity="0.6">TRACKER_LOCK: OK</text>
  </g>

  <!-- Left Sidebar HUD Stats -->
  <g transform="translate(20, 85)">
    <!-- Sidebar background grid -->
    <line x1="0" y1="0" x2="105" y2="0" stroke="#00f0ff" stroke-width="0.8" opacity="0.15" />
    <line x1="0" y1="98" x2="105" y2="98" stroke="#00f0ff" stroke-width="0.8" opacity="0.15" />
    
    <text x="0" y="14" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="9" opacity="0.7">ROIs ACTIVE</text>
    <text x="0" y="28" fill="#00f0ff" font-family="'Share Tech Mono', monospace" font-size="15" font-weight="bold">{len(detected_boxes):02d}</text>
    
    <text x="0" y="46" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="9" opacity="0.7">TOTAL_COMMITS</text>
    <text x="0" y="60" fill="#ffffff" font-family="'Share Tech Mono', monospace" font-size="15" font-weight="bold">{total_commits}</text>
    
    <text x="0" y="78" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="9" opacity="0.7">SCAN_STEPS</text>
    <text x="0" y="92" fill="#bd00ff" font-family="'Share Tech Mono', monospace" font-size="13" font-weight="bold">53 x 7 px</text>
  </g>

  <!-- Main contribution grid elements -->
  <g>
    <!-- Grid corner outline borders -->
    <path d="M {GRID_X0-8}, {GRID_Y0-8} L {GRID_X0-8}, {GRID_Y0-2} M {GRID_X0-8}, {GRID_Y0-8} L {GRID_X0-2}, {GRID_Y0-8}" fill="none" stroke="#00f0ff" stroke-width="1.2" opacity="0.5" />
    <path d="M {GRID_X0+grid_width+8}, {GRID_Y0-8} L {GRID_X0+grid_width+8}, {GRID_Y0-2} M {GRID_X0+grid_width+8}, {GRID_Y0-8} L {GRID_X0+grid_width+2}, {GRID_Y0-8}" fill="none" stroke="#00f0ff" stroke-width="1.2" opacity="0.5" />
    <path d="M {GRID_X0-8}, {GRID_Y0+grid_height+8} L {GRID_X0-8}, {GRID_Y0+grid_height+2} M {GRID_X0-8}, {GRID_Y0+grid_height+8} L {GRID_X0-2}, {GRID_Y0+grid_height+8}" fill="none" stroke="#00f0ff" stroke-width="1.2" opacity="0.5" />
    <path d="M {GRID_X0+grid_width+8}, {GRID_Y0+grid_height+8} L {GRID_X0+grid_width+8}, {GRID_Y0+grid_height+2} M {GRID_X0+grid_width+8}, {GRID_Y0+grid_height+8} L {GRID_X0+grid_width+2}, {GRID_Y0+grid_height+8}" fill="none" stroke="#00f0ff" stroke-width="1.2" opacity="0.5" />

    <!-- Grid headers (Months) -->
{months_joined}

    <!-- Row headers (Days) -->
    <text x="{GRID_X0 - 30}" y="{GRID_Y0 + 1 * STEP - 2}" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="8" opacity="0.6">Mon</text>
    <text x="{GRID_X0 - 30}" y="{GRID_Y0 + 3 * STEP - 2}" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="8" opacity="0.6">Wed</text>
    <text x="{GRID_X0 - 30}" y="{GRID_Y0 + 5 * STEP - 2}" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="8" opacity="0.6">Fri</text>

    <!-- Contribution squares -->
{squares_joined}

    <!-- Dynamic Bounding Boxes -->
{boxes_joined}

    <!-- Moving Laser Scanner -->
    <g class="laser-scanner">
      <!-- Gradient trail sweep -->
      <rect x="{GRID_X0 - 80}" y="{GRID_Y0 - 6}" width="80" height="{grid_height + 12}" fill="url(#laser-grad)" pointer-events="none" />
      <!-- Glow laser line -->
      <line x1="{GRID_X0}" y1="{GRID_Y0 - 6}" x2="{GRID_X0}" y2="{GRID_Y0 + grid_height + 6}" stroke="#00f0ff" stroke-width="2" filter="url(#cyan-glow)" pointer-events="none" />
    </g>
  </g>

  <!-- Bottom Terminal Logs & Legend -->
  <g>
    <!-- Log Output Console Box -->
    <rect x="130" y="{GRID_Y0 + grid_height + 14}" width="420" height="52" fill="#06090e" stroke="#1f2937" stroke-width="1" rx="4" opacity="0.9" />
{logs_joined}

    <!-- Color Legend -->
    <g transform="translate({svg_width - 290}, {GRID_Y0 + grid_height + 22})">
      <text x="0" y="8" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="9" opacity="0.7">INTENSITY_MAP:</text>
      
      <rect x="90" y="0" width="10" height="10" rx="1" ry="1" fill="#121620" />
      <text x="94" y="-4" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="6" opacity="0.5" text-anchor="middle">0</text>
      
      <rect x="110" y="0" width="10" height="10" rx="1" ry="1" fill="#00f0ff" filter="url(#cyan-glow)" />
      <text x="115" y="-4" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="6" opacity="0.5" text-anchor="middle">1-2</text>
      
      <rect x="130" y="0" width="10" height="10" rx="1" ry="1" fill="#bd00ff" filter="url(#purple-glow)" />
      <text x="135" y="-4" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="6" opacity="0.5" text-anchor="middle">3-5</text>
      
      <rect x="150" y="0" width="10" height="10" rx="1" ry="1" fill="#ff007a" filter="url(#pink-glow)" />
      <text x="155" y="-4" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="6" opacity="0.5" text-anchor="middle">6-8</text>
      
      <rect x="170" y="0" width="10" height="10" rx="1" ry="1" fill="#ffffff" filter="url(#white-glow)" />
      <text x="175" y="-4" fill="#58a6ff" font-family="'Share Tech Mono', monospace" font-size="6" opacity="0.5" text-anchor="middle">9+</text>
      
      <!-- BBox Legend -->
      <g transform="translate(0, 18)">
        <rect x="0" y="0" width="8" height="8" fill="none" stroke="#39ff14" stroke-width="1.2" stroke-dasharray="1,1" />
        <text x="12" y="7" fill="#39ff14" font-family="'Share Tech Mono', monospace" font-size="8" font-weight="bold">COMMIT_CLUSTER</text>

        <rect x="90" y="0" width="8" height="8" fill="none" stroke="#00f0ff" stroke-width="1.2" stroke-dasharray="1,1" />
        <text x="102" y="7" fill="#00f0ff" font-family="'Share Tech Mono', monospace" font-size="8" font-weight="bold">DEV_STREAK</text>

        <rect x="160" y="0" width="8" height="8" fill="none" stroke="#ff007a" stroke-width="1.2" stroke-dasharray="1,1" />
        <text x="172" y="7" fill="#ff007a" font-family="'Share Tech Mono', monospace" font-size="8" font-weight="bold">PEAK_BURST</text>
      </g>
    </g>
  </g>
</svg>
"""
    return svg_content

def main():
    token = os.environ.get("GITHUB_TOKEN")
    
    # Ensure dist folder exists
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    calendar_data = fetch_contributions(USERNAME, token)
    svg_content = generate_svg(calendar_data)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(svg_content)
        
    print(f"Successfully generated HUD SVG and saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
