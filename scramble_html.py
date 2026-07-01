import os
import shutil
import uuid

def scramble():
    in_dir = "data/raw/synthetic_shasta"
    out_dir = "data/raw/scrambled_shasta"
    
    os.makedirs(out_dir, exist_ok=True)
    
    # clear out dir
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))
        
    mapping = {}
    
    for f in os.listdir(in_dir):
        if not f.endswith(".html"):
            continue
            
        random_name = str(uuid.uuid4())[:8] + ".html"
        src = os.path.join(in_dir, f)
        dst = os.path.join(out_dir, random_name)
        
        shutil.copy(src, dst)
        mapping[random_name] = f
        
    # save mapping for debugging (AFR-1 will not read this)
    with open(os.path.join(out_dir, "_truth_mapping.txt"), "w") as out:
        for r, t in mapping.items():
            out.write(f"{r} -> {t}\n")
            
if __name__ == "__main__":
    scramble()
