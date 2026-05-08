import sys
sys.stdout.reconfigure(encoding='utf-8')
from crawler import perform_search
print("Searching...")
results = perform_search("Lun-class MD-160", max_results=1)
print(f"Results: {results}")
