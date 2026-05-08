
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.getcwd())

from crawler import perform_search, scrape_url_text, extract_facts_from_chunk, consolidate_facts
from openai import OpenAI

def debug_extraction(craft_name):
    client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama', max_retries=0)
    
    print(f"[*] Debugging: {craft_name}")
    
    results = perform_search(craft_name, max_results=1)
    if not results:
        print("[-] No results found.")
        return
        
    url = results[0].get('href')
    print(f"[*] URL: {url}")
    
    text = scrape_url_text(url)
    print(f"[*] Text length: {len(text)}")
    
    # Use Map-Reduce logic from crawler.py
    chunk_size = 4000
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    all_facts = []
    
    print(f"[*] Text split into {len(chunks)} chunks.")
    
    from crawler import extract_facts_from_chunk, consolidate_facts
    
    for idx, chunk in enumerate(chunks):
        part_num = idx + 1
        print(f"[*] Processing part {part_num}/{len(chunks)}...")
        
        chunk_facts = extract_facts_from_chunk(chunk, client, craft_name, part_num, len(chunks))
        if chunk_facts:
            all_facts.extend(chunk_facts)
            print(f"[+] Part {part_num} OK ({len(chunk_facts)} facts).")
        else:
            print(f"[-] Part {part_num} FAILED or NO FACTS.")
    
    if all_facts:
        print(f"[*] Consolidating {len(all_facts)} facts...")
        final_extraction = consolidate_facts(all_facts, client, craft_name)
    else:
        final_extraction = None
    
    if final_extraction:
        print("[+] SUCCESS: Extraction worked.")
        print(final_extraction.model_dump_json(indent=2))
    else:
        print("[-] FAILED: Extraction returned None for all parts.")

if __name__ == '__main__':
    debug_extraction('Lun-class MD-160')
