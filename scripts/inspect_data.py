"""Dump the schema and a sample of each downloaded file.

Run once after download to learn the real column names before building anything.
"""
import pyarrow.feather as feather
import pyarrow as pa
from fbg.data import SOURCES


def describe(name, path):
    print(f"\n{'='*70}\n{name}  —  {path.name}\n{'='*70}")
    table = feather.read_table(path, memory_map=True)
    print(f"rows: {table.num_rows:,}   columns: {table.num_columns}   "
          f"in-memory: {table.nbytes/1e9:.2f} GB")
    print("\nschema:")
    for field in table.schema:
        print(f"  {field.name:<28} {field.type}")
    print("\nfirst 5 rows:")
    head = table.slice(0, 5).to_pydict()
    for col, vals in head.items():
        shown = ", ".join(str(v)[:30] for v in vals)
        print(f"  {col:<28} {shown}")
    return table


if __name__ == "__main__":
    for name, src in SOURCES.items():
        if src.path.exists():
            t = describe(name, src.path)
            # for the small metadata files, show value distributions on key columns
            if src.approx_mb < 100:
                for col in t.schema.names:
                    if any(k in col.lower() for k in ("type", "class", "side", "consensus", "nt")):
                        try:
                            vc = t.column(col).value_counts().to_pylist()
                            top = sorted(vc, key=lambda d: -d["counts"])[:8]
                            print(f"\n  top values in '{col}':")
                            for d in top:
                                print(f"    {str(d['values'])[:40]:<42} {d['counts']:>8,}")
                        except Exception:
                            pass
        else:
            print(f"\n{name}: not downloaded yet")
