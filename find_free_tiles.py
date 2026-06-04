import os

def find_free():
    base_dir = os.path.dirname(__file__)
    csv_path = os.path.join(base_dir, "static", "assets", "the_ville", "matrix", "maze", "collision_maze.csv")
    
    with open(csv_path, "r") as f:
        csv_raw = f.read().strip()
    csv_values = [int(v.strip()) for v in csv_raw.split(",") if v.strip()]
    
    width = 140
    height = 100
    
    def is_free(x, y):
        if 0 <= x < width and 0 <= y < height:
            return csv_values[y * width + x] == 0
        return False

    targets = {
        "The Rose and Crown Pub / Crow Home": (57, 22),
        "Harvey Oak Supply": (63, 47),
    }
    
    print("=== Finding closest free tiles ===")
    for name, (tx, ty) in targets.items():
        found = False
        # 从距离为 1 到 5 搜索
        for r in range(1, 6):
            candidates = []
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    nx, ny = tx + dx, ty + dy
                    if is_free(nx, ny):
                        dist = abs(dx) + abs(dy)
                        candidates.append((nx, ny, dist))
            if candidates:
                # 按曼哈顿距离排序
                candidates.sort(key=lambda item: item[2])
                best_x, best_y, best_d = candidates[0]
                print(f"Target '{name}' original ({tx}, {ty}) -> Best walkable tile: ({best_x}, {best_y}) at distance {best_d}")
                found = True
                break
        if not found:
            print(f"Target '{name}' original ({tx}, {ty}) -> No walkable tile found in range 5!")

if __name__ == "__main__":
    find_free()
