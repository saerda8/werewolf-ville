"""Map, collision, scene, and pathfinding helpers for the game engine."""

import os
import sys
from collections import deque


PUBLIC_PLAZA_COLLISION_FREE_TILES = {
    # The Tiled collision layer has an invisible vertical seam here. Visually this
    # is open plaza/road, so treating it as blocked splits the morning circle.
    (51, y) for y in range(40, 51)
} | {
    # Hobbs Cafe has a visually open passage here; keep NPCs from getting pinned at the counter.
    (76, 20), (77, 20)
} | {
    # The sheriff office's right prison cell has an invisible wall seam across
    # its doorway. Open only the door tiles so prison escort uses real walking.
    (25, 68), (25, 69)
}


def load_collision_maze():
    """加载碰撞迷宫数据（单行CSV，140x100 格）"""
    maze_path = os.path.join(
        os.path.dirname(__file__), "static", "assets", "the_ville",
        "matrix", "maze", "collision_maze.csv"
    )
    if not os.path.exists(maze_path):
        print("[WARN] collision_maze.csv not found, collision disabled", file=sys.stderr, flush=True)
        return None

    with open(maze_path, "r") as f:
        raw = f.read().strip()
    values = [int(v.strip()) for v in raw.split(",") if v.strip()]

    width = 140
    height = 100
    if len(values) != width * height:
        print(f"[WARN] collision_maze values={len(values)}, expected={width*height}", file=sys.stderr, flush=True)
        return None

    maze = []
    for i in range(height):
        row = values[i * width : (i + 1) * width]
        maze.append(row)

    _apply_collision_overrides(maze)
    return maze


def _apply_collision_overrides(maze):
    """Normalize known invisible collision artifacts in public outdoor spaces."""
    if not maze:
        return maze
    height = len(maze)
    width = len(maze[0]) if height else 0
    for x, y in PUBLIC_PLAZA_COLLISION_FREE_TILES:
        if 0 <= x < width and 0 <= y < height:
            maze[y][x] = 0
    return maze


def _connect_maze_regions(maze, width, height):
    """打通碰撞迷宫中不连通区域之间的墙壁，使地图连通"""
    def flood_fill(start):
        visited = set()
        visited.add(start)
        queue = deque([start])
        while queue:
            cx, cy = queue.popleft()
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited and maze[ny][nx] == 0:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        return visited

    visited = set()
    components = []
    for y in range(height):
        for x in range(width):
            if maze[y][x] == 0 and (x, y) not in visited:
                comp = flood_fill((x, y))
                visited.update(comp)
                components.append(comp)

    if len(components) <= 1:
        return maze

    components.sort(key=len, reverse=True)
    main_comp = components[0]

    for comp in components[1:]:
        best_wall = None
        best_dist = float("inf")
        comp_list = list(comp)
        sample_step = max(1, len(comp_list) // 50)
        sample_points = comp_list[::sample_step]

        for (cx, cy) in sample_points:
            for (dx, dy) in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                wx, wy = cx + dx, cy + dy
                steps = 0
                while 0 <= wx < width and 0 <= wy < height and steps < 15:
                    if maze[wy][wx] == 0:
                        if (wx, wy) in main_comp:
                            wx2, wy2 = cx + dx, cy + dy
                            walls = []
                            while 0 <= wx2 < width and 0 <= wy2 < height and maze[wy2][wx2] != 0:
                                walls.append((wx2, wy2))
                                wx2 += dx
                                wy2 += dy
                            if walls and len(walls) < best_dist:
                                best_dist = len(walls)
                                best_wall = walls
                        break
                    wx += dx
                    wy += dy
                    steps += 1

        if best_wall:
            mid = len(best_wall) // 2
            for i in range(max(0, mid - 1), min(len(best_wall), mid + 1)):
                wx, wy = best_wall[i]
                maze[wy][wx] = 0
            main_comp = main_comp | comp
            for wx, wy in best_wall[max(0, mid - 1):min(len(best_wall), mid + 1)]:
                main_comp.add((wx, wy))

    return maze


def bfs_path(maze, start, end, max_steps=50000):
    """BFS 寻路，返回路径列表 [(x,y), ...] 或 None"""
    if not maze:
        return None
    height = len(maze)
    width = len(maze[0]) if height > 0 else 0
    sx, sy = start
    ex, ey = end

    if sx < 0 or sx >= width or sy < 0 or sy >= height:
        return None
    if ex < 0 or ex >= width or ey < 0 or ey >= height:
        return None
    if maze[sy][sx] != 0 or maze[ey][ex] != 0:
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                nx, ny = ex + dx, ey + dy
                if 0 <= nx < width and 0 <= ny < height and maze[ny][nx] == 0:
                    ex, ey = nx, ny
                    break
            else:
                continue
            break
        else:
            return None

    if (sx, sy) == (ex, ey):
        return []

    visited = {(sx, sy): None}
    queue = deque([(sx, sy)])
    steps = 0

    while queue and steps < max_steps:
        cx, cy = queue.popleft()
        steps += 1
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited and maze[ny][nx] == 0:
                visited[(nx, ny)] = (cx, cy)
                if (nx, ny) == (ex, ey):
                    path = []
                    pos = (ex, ey)
                    while pos is not None and pos != (sx, sy):
                        path.append(pos)
                        pos = visited[pos]
                    path.reverse()
                    return path
                queue.append((nx, ny))
    return None


def load_scene_data():
    """
    加载 sector / arena / game_object 数据
    返回: (sector_maze, arena_maze, go_maze, sector_dict, arena_dict, go_dict)
    格式同 collision_maze: 140x100 二维数组，每个值映射到文字名
    """
    base = os.path.join(os.path.dirname(__file__), "static", "assets", "the_ville", "matrix")
    maze_dir = os.path.join(base, "maze")
    blocks_dir = os.path.join(base, "special_blocks")

    def load_maze_csv(name):
        path = os.path.join(maze_dir, name)
        if not os.path.exists(path):
            print(f"[WARN] {name} not found", file=sys.stderr, flush=True)
            return [[0] * 140 for _ in range(100)]
        with open(path, "r") as f:
            raw = f.read().strip()
        vals = [int(v.strip()) for v in raw.split(",") if v.strip()]
        maze = []
        for i in range(100):
            maze.append(vals[i * 140:(i + 1) * 140])
        return maze

    def load_blocks_csv(name):
        path = os.path.join(blocks_dir, name)
        d = {}
        if not os.path.exists(path):
            print(f"[WARN] {name} not found", file=sys.stderr, flush=True)
            return d
        with open(path, "r") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    d[int(parts[0])] = parts[-1].strip()
        return d

    sector_maze = load_maze_csv("sector_maze.csv")
    arena_maze = load_maze_csv("arena_maze.csv")
    go_maze = load_maze_csv("game_object_maze.csv")

    sector_dict = load_blocks_csv("sector_blocks.csv")
    arena_dict = load_blocks_csv("arena_blocks.csv")
    go_dict = load_blocks_csv("game_object_blocks.csv")

    return sector_maze, arena_maze, go_maze, sector_dict, arena_dict, go_dict


def get_tile_scene(x, y, sector_maze, arena_maze, go_maze, sector_dict, arena_dict, go_dict):
    """获取某个格子的场景信息"""
    result = {"sector": "", "arena": "", "game_objects": []}
    if 0 <= x < 140 and 0 <= y < 100:
        sid = sector_maze[y][x]
        aid = arena_maze[y][x]
        gid = go_maze[y][x]
        if sid in sector_dict:
            result["sector"] = sector_dict[sid]
        if aid in arena_dict:
            result["arena"] = arena_dict[aid]
        if gid in go_dict:
            result["game_objects"] = [go_dict[gid]]
    return result


def get_nearby_objects(x, y, radius, sector_maze, arena_maze, go_maze, sector_dict, arena_dict, go_dict):
    """获取某位置周围的可见物件列表（去重）"""
    objects = set()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = x + dx, y + dy
            info = get_tile_scene(
                nx, ny, sector_maze, arena_maze, go_maze,
                sector_dict, arena_dict, go_dict
            )
            for obj in info["game_objects"]:
                objects.add(obj)
    return sorted(objects)
