import asyncio
import os
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client
from tools.mcp_client import mcp_query_nl_to_sql
from ruto_agent import chat

load_dotenv()

# Helper: escape single quotes for SQL literals
def esc(s: str) -> str:
    if s is None:
        return ''
    return s.replace("'", "''")

# Remove Slack user mentions like <@U08MPQJ878X>
MENTION_RE = re.compile(r"<@[^>]+>\s*")

def clean_parent_message(text: str) -> str:
    if not text:
        return ''
    cleaned = MENTION_RE.sub('', text).strip()
    return cleaned

async def process_batch(limit: int = 100, dry_run: bool = False):
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set in the environment')

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Destination tables are expected to already exist; no DDL executed here.

    # Fetch the first `limit` rows from productobot.slack_threads using run_sql.
    # We pack multiple fields into a single JSON column (full_json) so the RPC signature is 5 columns (text, text, jsonb, double precision, double precision).
    select_sql = f"""
    SELECT
      id::text AS id,
      thread_ts::text AS thread_ts,
      channel_id::text AS text_col2,
      to_jsonb(json_build_object(
        'parent_message', parent_message,
        'parent_user_id', parent_user_id,
        'reply_count', reply_count,
        'thread_timestamp', thread_timestamp,
        'parent_user_name', parent_user_name
      )) AS full_json,
      0.0::double precision AS distance
    FROM productobot.slack_threads
    ORDER BY id::bigint ASC
    LIMIT {limit};
    """
    print('Running query to fetch threads (RPC run_sql)...')
    resp = supabase.rpc('run_sql', {'query': select_sql}).execute()
    rows = resp.data or []

    print(f'Fetched {len(rows)} rows')

    for row in rows:
        thread_id = row.get('id')
        thread_ts = row.get('thread_ts')

        # full_json contains packed fields we need to extract
        full_json = row.get('full_json') or {}
        if isinstance(full_json, str):
            try:
                info = json.loads(full_json)
            except Exception:
                # Fallback: try to unquote and parse
                try:
                    info = json.loads(full_json.strip('"'))
                except Exception:
                    info = {}
        else:
            info = full_json if isinstance(full_json, dict) else {}

        # Robustly extract thread_ts and channel_id: MCP RPC can return unexpected key names, so
        # try likely keys first and then fall back to pattern matching values in the row.
        def _guess_value(row: dict, key_names: list, pattern=None):
            # Try canonical keys
            for k in key_names:
                if k in row and row.get(k):
                    return row.get(k)
            # Try keys in packed info
            for k in key_names:
                if isinstance(info, dict) and k in info and info.get(k):
                    return info.get(k)
            # Pattern match any string value in row
            if pattern is not None:
                pat = pattern
                for v in row.values():
                    if isinstance(v, str) and pat.match(v.strip()):
                        return v.strip()
                if isinstance(info, dict):
                    for v in info.values():
                        if isinstance(v, str) and pat.match(v.strip()):
                            return v.strip()
            return None

        THREAD_TS_RE = re.compile(r'^\d{9,}\.\d+$')
        CHANNEL_RE = re.compile(r'^C[A-Z0-9]{7,}$')

        thread_ts = _guess_value(row, ['thread_ts', 'text_col', 'narrative_text'], THREAD_TS_RE) or ''
        channel_id = _guess_value(row, ['channel_id', 'text_col2', 'city'], CHANNEL_RE) or ''
        raw_message = info.get('parent_message') or ''
        parent_user_id = info.get('parent_user_id') or ''
        parent_user_name = info.get('parent_user_name') or ''
        thread_timestamp = info.get('thread_timestamp')
        reply_count_val = info.get('reply_count') or row.get('reply_count') or 0

        # Normalize raw_message
        if isinstance(raw_message, (dict, list)):
            raw_message = json.dumps(raw_message, ensure_ascii=False)
        elif isinstance(raw_message, str) and raw_message.startswith('"') and raw_message.endswith('"'):
            raw_message = raw_message[1:-1]
        cleaned_prompt = clean_parent_message(raw_message)
        if not cleaned_prompt:
            print(f'Skipping thread id={thread_id} because cleaned prompt is empty')
            continue

        # thread_ts is required in the *_mcp table (unique, not null); skip rows without it
        if not thread_ts:
            print(f"Skipping thread id={thread_id} because thread_ts is missing")
            continue

        print('---')
        print(f'Thread id={thread_id} thread_ts={thread_ts} channel={channel_id}')
        print('Prompt:', cleaned_prompt)

        try:
            # Call the chat flow (this prefers MCP and falls back to agents)
            response_text = await chat(query=cleaned_prompt, channel_id=channel_id, thread_ts=thread_ts, chatbot_status='on', first_name=parent_user_name or 'BatchBot')
            print('Response (preview):', (response_text or '')[:200])
        except Exception as e:
            print(f'Error calling chat() for thread {thread_id}:', e)
            response_text = None

        if dry_run:
            print('Dry run - not writing to DB')
            continue

        # Prepare thread_timestamp value (use now() if original is missing)
        ts_sql_value = "now()"
        if thread_timestamp:
            ts_sql_value = f"'{esc(str(thread_timestamp))}'"

        # Insert into slack_threads_mcp (do nothing on conflict thread_ts)
        # Insert (or update) into slack_threads_mcp and RETURN the row in a 5-column shape
        # Attempt to preserve original thread id so replies can reference the same numeric id.
        id_sql_part = ''
        id_columns_part = ''
        try:
            orig_id_int = int(thread_id)
            id_sql_part = f"{orig_id_int}, "
            id_columns_part = 'id, '
        except Exception:
            orig_id_int = None

        new_thread_id = None

        # If we have an original numeric id, prefer to reuse it if a row with that id already exists.
        if orig_id_int is not None:
            sel_by_id_sql = (
                f"SELECT id::text AS id, thread_ts::text AS text_col, channel_id::text AS text_col2, "
                f"to_jsonb(parent_message) AS full_json, 0.0::double precision AS distance "
                f"FROM productobot.slack_threads_mcp WHERE id = {orig_id_int} LIMIT 1;"
            )
            sel_by_id_resp = supabase.rpc('run_sql', {'query': sel_by_id_sql}).execute()
            if sel_by_id_resp.data and len(sel_by_id_resp.data) > 0:
                # Row with this id exists — update it with the latest data and return it
                upd_sql = (
                    f"UPDATE productobot.slack_threads_mcp SET thread_ts = '{esc(thread_ts)}', channel_id = '{esc(channel_id)}', parent_message = '{esc(cleaned_prompt)}', parent_user_id = '{esc(parent_user_id)}', reply_count = {int(row.get('reply_count') or 0)}, thread_timestamp = {ts_sql_value}, parent_user_name = '{esc(parent_user_name)}', updated_at = now() WHERE id = {orig_id_int} RETURNING id::text AS id, thread_ts::text AS text_col, channel_id::text AS text_col2, to_jsonb(parent_message) AS full_json, 0.0::double precision AS distance;"
                )
                try:
                    upd_resp = supabase.rpc('run_sql', {'query': upd_sql}).execute()
                    if upd_resp.data and len(upd_resp.data) > 0:
                        try:
                            new_thread_id = int(upd_resp.data[0].get('id'))
                            print(f'Reused existing slack_threads_mcp id={new_thread_id} for original id={orig_id_int}')
                        except Exception:
                            new_thread_id = None
                    else:
                        print(f'Warning: update by id {orig_id_int} did not return a row')
                except Exception as e:
                    print(f'Error updating existing slack_threads_mcp id={orig_id_int}:', e)

        # If id wasn't reused/updated above, attempt to insert (with id if present)
        if new_thread_id is None:
            insert_threads_mcp = (
                f"INSERT INTO productobot.slack_threads_mcp ({id_columns_part}thread_ts, channel_id, parent_message, parent_user_id, reply_count, thread_timestamp, parent_user_name)"
                f" VALUES ({id_sql_part}'{esc(thread_ts)}', '{esc(channel_id)}', '{esc(cleaned_prompt)}', '{esc(parent_user_id)}', {int(row.get('reply_count') or 0)}, {ts_sql_value}, '{esc(parent_user_name)}')"
                " ON CONFLICT (thread_ts) DO UPDATE SET id = COALESCE(productobot.slack_threads_mcp.id, EXCLUDED.id), parent_message = EXCLUDED.parent_message, updated_at = now()"
                " RETURNING id::text AS id, thread_ts::text AS text_col, channel_id::text AS text_col2, to_jsonb(parent_message) AS full_json, 0.0::double precision AS distance;"
            )
            try:
                insert_resp = supabase.rpc('run_sql', {'query': insert_threads_mcp}).execute()
                # If the INSERT ... RETURNING returned a row, extract the id directly
                if insert_resp.data and len(insert_resp.data) > 0:
                    try:
                        new_thread_id = int(insert_resp.data[0].get('id'))
                        if orig_id_int is not None and new_thread_id == orig_id_int:
                            print(f'Inserted slack_threads_mcp with preserved id={new_thread_id}')
                    except Exception:
                        new_thread_id = None
                else:
                    # Fallback: attempt to select the row by thread_ts (5-column shape)
                    sel_sql = (
                        f"SELECT id::text AS id, thread_ts::text AS text_col, channel_id::text AS text_col2, to_jsonb(parent_message) AS full_json, 0.0::double precision AS distance "
                        f"FROM productobot.slack_threads_mcp WHERE thread_ts = '{esc(thread_ts)}' LIMIT 1;"
                    )
                    sel_resp = supabase.rpc('run_sql', {'query': sel_sql}).execute()
                    if sel_resp.data and len(sel_resp.data) > 0:
                        try:
                            new_thread_id = int(sel_resp.data[0].get('id'))
                        except Exception:
                            new_thread_id = None
                    else:
                        print(f'Warning: could not resolve id in slack_threads_mcp for thread_ts={thread_ts}')
            except Exception as e:
                print(f'Error inserting/fetching slack_threads_mcp for thread {thread_id}:', e)

        # Insert reply into slack_replies_mcp using the MCP threads table id (do not reference original table)
        if response_text and new_thread_id:
            message_ts = datetime.utcnow().isoformat() + 'Z'
            insert_reply_sql = (
                "INSERT INTO productobot.slack_replies_mcp (thread_id, user_id, message_text, reply_timestamp, message_ts, user_name)"
                f" VALUES ({int(new_thread_id)}, 'productobot_mcp', '{esc(response_text)}', now(), '{esc(message_ts)}', 'ProductoBot MCP')"
                " ON CONFLICT (thread_id, message_ts) DO NOTHING"
                " RETURNING id::text AS id, thread_id::text AS text_col, message_ts::text AS text_col2, to_jsonb(message_text) AS full_json, 0.0::double precision AS distance;"
            )
            try:
                insert_reply_resp = supabase.rpc('run_sql', {'query': insert_reply_sql}).execute()
                if not (insert_reply_resp.data and len(insert_reply_resp.data) > 0):
                    print(f'Warning: reply insert did not return rows for slack_threads_mcp id {new_thread_id}')
            except Exception as e:
                print(f'Error inserting reply for slack_threads_mcp id {new_thread_id}:', e)
        else:
            print(f'Skipping reply insertion for original thread {thread_id} because slack_threads_mcp id not resolved or no response')

    print('Batch processing completed')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run MCP/chat on first N slack threads and save inputs/outputs to MCP tables')
    parser.add_argument('--limit', type=int, default=100, help='Number of threads to process')
    parser.add_argument('--dry-run', action='store_true', help='Do not write to the database, just print what would happen')

    args = parser.parse_args()

    asyncio.run(process_batch(limit=args.limit, dry_run=args.dry_run))
