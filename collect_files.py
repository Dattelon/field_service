import os

OUTPUT_FILE = "project_snapshot.txt"

#   
INCLUDE_EXT = {".py", ".md", ".txt", ".yml", ".yaml", ".env", ".json", ".csv"}


def should_include_file(filename: str) -> bool:
    """     ."""
    _, ext = os.path.splitext(filename)
    return ext in INCLUDE_EXT or filename in (
        ".env",
        "requirements.txt",
        "docker-compose.yml",
    )


def write_tree(root_dir: str, out):
    """    ."""
    out.write(" \n")
    out.write("=" * 80 + "\n")

    for dirpath, dirnames, filenames in os.walk(root_dir):
        #    (.venv, .git  ..)
        if any(part.startswith(".") for part in dirpath.split(os.sep)):
            continue

        level = dirpath.replace(root_dir, "").count(os.sep)
        indent = "    " * level
        dirname = (
            os.path.basename(dirpath)
            if dirpath != root_dir
            else os.path.basename(root_dir)
        )
        out.write(f"{indent}{dirname}/\n")

        subindent = "    " * (level + 1)
        for fname in sorted(filenames):
            out.write(f"{subindent}{fname}\n")

    out.write("\n\n")


def collect_files(root_dir: str):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        #  
        write_tree(root_dir, out)

        #   
        for dirpath, _, filenames in os.walk(root_dir):
            #   
            if any(part.startswith(".") for part in dirpath.split(os.sep)):
                continue

            for fname in sorted(filenames):
                if should_include_file(fname):
                    full_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(full_path, root_dir)
                    try:
                        with open(
                            full_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            content = f.read()
                    except Exception as e:
                        content = f"<<   : {e}>>"

                    out.write(f"\n{'='*80}\n")
                    out.write(f": {rel_path}\n")
                    out.write(f"{'='*80}\n")
                    out.write(content)
                    out.write("\n\n")


if __name__ == "__main__":
    project_root = os.path.dirname(os.path.abspath(__file__))
    collect_files(project_root)
    print(f"      {OUTPUT_FILE}")
