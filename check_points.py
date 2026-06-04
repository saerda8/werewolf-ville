import os
import sys

# 动态添加当前目录
sys.path.insert(0, os.path.dirname(__file__))

def check():
    base_dir = os.path.dirname(__file__)
    csv_path = os.path.join(base_dir, "static", "assets", "the_ville", "matrix", "maze", "collision_maze.csv")
    
    with open(csv_path, "r") as f:
        csv_raw = f.read().strip()
    csv_values = [int(v.strip()) for v in csv_raw.split(",") if v.strip()]
    
    width = 140
    
    # 动态从 game_engine 中加载实际配置
    from game_engine import LANDMARKS, AGENT_CONFIGS
    
    def is_free(x, y):
        return csv_values[y * width + x] == 0

    print("=== Landmark Collision Check ===")
    all_ok = True
    for name, pos in LANDMARKS.items():
        x, y = pos["x"], pos["y"]
        val = csv_values[y * width + x]
        status = "BLOCKED (Wall) ❌" if val != 0 else "FREE (Walkable)  "
        if val != 0:
            all_ok = False
        print(f"Landmark '{name:25s}' at ({x:3d}, {y:3d}) is {status} (val={val})")
        
    print("\n=== Agent Home Collision Check ===")
    for name, cfg in AGENT_CONFIGS.items():
        x, y = cfg["home"]["x"], cfg["home"]["y"]
        val = csv_values[y * width + x]
        status = "BLOCKED (Wall) ❌" if val != 0 else "FREE (Walkable)  "
        if val != 0:
            all_ok = False
        print(f"Agent '{name:20s}' home at ({x:3d}, {y:3d}) is {status} (val={val})")

    if all_ok:
        print("\n🎉 SUCCESS! All customized coordinates are 100% free and walkable in the collision maze!")
    else:
        print("\n❌ FAILURE! Some coordinates are still blocked by walls!")

if __name__ == "__main__":
    check()
