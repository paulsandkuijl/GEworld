with open('app/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

missing = (
    "                ingest_to_db(extraction, final_url, existing_craft=existing)\n"
    "                saved_id = existing.id\n"
    "            else:\n"
    "                yield event('Creating new entry: ' + extracted_name)\n"
    "                new_craft = Craft(name=extracted_name, status='In Database Queue', data_confidence_score=0.0)\n"
    "                db.add(new_craft)\n"
    "                db.commit()\n"
    "                db.refresh(new_craft)\n"
    "                ingest_to_db(extraction, final_url, existing_craft=new_craft)\n"
    "                saved_id = new_craft.id\n"
    "\n"
    "            import json as _json\n"
    "            done_payload = {'type': 'done', 'message': 'Saved: ' + extracted_name,\n"
    "                            'craft_id': saved_id, 'craft_name': extracted_name,\n"
    "                            'source_url': final_url, 'auto_searched': search_mode}\n"
    "            yield 'data: ' + _json.dumps(done_payload) + '\n\n'\n"
    "\n"
    "        except Exception as e:\n"
    "            yield event('Unexpected error: ' + str(e), type='error')\n"
    "        finally:\n"
    "            db.close()\n"
    "\n"
    "    from fastapi.responses import StreamingResponse\n"
    "    return StreamingResponse(stream(), media_type='text/event-stream',\n"
    "                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})\n"
)

content = content.rstrip() + '\n' + missing

with open('app/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done — stream function tail appended.')
