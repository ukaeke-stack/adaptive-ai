"""Bounded deterministic handlers for additional text/data actions."""
import csv, difflib, html, io, json, re, statistics, textwrap, unicodedata, uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote, urlparse

MAX_ITEMS = 500
MAX_TEXT = 120000

def execute_extra(action, step, value):
    lines = value.splitlines()
    if action == "text_statistics":
        words = re.findall(r"\b[\w’'-]+\b", value, re.UNICODE)
        return {"status":"succeeded","characters":len(value),"characters_without_whitespace":sum(not c.isspace() for c in value),"words":len(words),"unique_words":len(set(w.casefold() for w in words)),"lines":len(lines),"paragraphs":len([p for p in re.split(r"\n\s*\n",value.strip()) if p.strip()])}
    if action == "diff_summary":
        other=step.get("second_input","")
        if not isinstance(other,str): return {"status":"failed","message":"second_input must be text."}
        diff=list(difflib.unified_diff(value.splitlines(),other.splitlines(),fromfile="input",tofile="second_input",lineterm=""))
        return {"status":"succeeded","diff_lines":diff[:MAX_ITEMS],"similarity":round(difflib.SequenceMatcher(None,value,other).ratio(),4)}
    if action in {"count_words_by_line","count_code_lines","paragraph_count","word_count_by_sentence"}:
        if action=="count_words_by_line": return {"status":"succeeded","lines":[{"line":i,"words":len(x.split())} for i,x in enumerate(lines[:MAX_ITEMS],1)],"count":len(lines)}
        if action=="count_code_lines": return {"status":"succeeded","total_lines":len(lines),"nonblank_lines":sum(bool(x.strip()) for x in lines),"blank_lines":sum(not x.strip() for x in lines)}
        if action=="paragraph_count": return {"status":"succeeded","count":len([p for p in re.split(r"\n\s*\n",value.strip()) if p.strip()])}
        items=[s for s in re.split(r"(?<=[.!?])\s+",value.strip()) if s]
        return {"status":"succeeded","sentences":[{"text":s,"words":len(s.split())} for s in items[:MAX_ITEMS]],"count":len(items)}
    patterns={
      "extract_emails":r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
      "extract_phone_numbers":r"(?<!\w)\+?\d[\d ().-]{5,}\d(?!\w)",
      "extract_ipv4_addresses":r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])",
      "extract_dates_iso":r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b",
      "extract_currency_amounts":r"(?i)(?:[$€£₦]|USD|EUR|GBP|NGN)\s?\d[\d,]*(?:\.\d{1,2})?",
      "extract_file_extensions":r"(?i)\b[\w.-]+\.([a-z0-9]{1,12})\b",
      "extract_todo_comments":r"(?im)^.*\b(?:TODO|FIXME|XXX|HACK)\b.*$",
      "extract_html_ids":r"""(?i)\bid=["']([^"']+)["']""",
      "extract_css_classes":r"""(?i)\bclass=["']([^"']+)["']""",
      "extract_html_images":r"""(?i)<img\b[^>]*src=["']([^"']+)["']""",
      "extract_html_forms":r"(?is)<form\b.*?</form\s*>",
      "extract_html_scripts":r"(?is)<script\b.*?</script\s*>",
      "extract_xml_tags":r"(?is)<([A-Za-z][\w:.-]*)\b[^>]*>",
      "extract_code_blocks":r"(?s)"+chr(96)*3+r".*?"+chr(96)*3,
      "extract_markdown_images":r"!\[([^\]]*)\]\(([^)]+)\)",
      "extract_numbered_lists":r"(?m)^\s*\d+[.)]\s+(.+)$",
      "extract_bullet_lists":r"(?m)^\s*[-*+]\s+(.+)$",
      "extract_file_paths":r"(?:[A-Za-z]:\\[^\s<>|]+|/[^\s<>|]+)",
      "extract_domains":r"(?i)(?:https?://)?([a-z0-9.-]+\.[a-z]{2,})",
    }
    if action in patterns:
        vals=re.findall(patterns[action],value,re.I)
        if vals and isinstance(vals[0],tuple): vals=[next((x for x in v if x),"") for v in vals]
        vals=list(dict.fromkeys(x for x in vals if x))
        return {"status":"succeeded","items":vals[:MAX_ITEMS],"count":len(vals)}
    if action in {"extract_initials","make_acronym"}:
        words=re.findall(r"[\w'-]+",value)
        key="initials" if action=="extract_initials" else "acronym"
        return {"status":"succeeded",key:"".join(w[0].upper() for w in words if w)}
    if action in {"extract_first_paragraph","extract_last_paragraph","paragraph_count"}:
        paras=[p for p in re.split(r"\n\s*\n",value.strip()) if p.strip()]
        if action=="extract_first_paragraph": return {"status":"succeeded","text":paras[0] if paras else ""}
        if action=="extract_last_paragraph": return {"status":"succeeded","text":paras[-1] if paras else ""}
        return {"status":"succeeded","count":len(paras)}
    if action in {"remove_empty_lines","number_lines","indent_text","dedent_text","truncate_text","expand_tabs","normalize_newlines","remove_control_characters","prefix_lines","suffix_lines","join_lines","reverse_words","split_words","alphabetize_words","find_duplicate_words","find_long_words","extract_lines_matching","exclude_lines_matching"}:
        if action=="remove_empty_lines": result="\n".join(x for x in lines if x.strip())
        elif action=="number_lines": result="\n".join(f"{i}. {x}" for i,x in enumerate(lines,1))
        elif action=="indent_text": result=textwrap.indent(value,str(step.get("prefix","    "))[:32])
        elif action=="dedent_text": result=textwrap.dedent(value)
        elif action=="truncate_text":
            n=step.get("limit",500)
            if not isinstance(n,int) or not 1<=n<=MAX_TEXT: return {"status":"failed","message":"limit must be from 1 to 120000."}
            result=value[:n]
        elif action=="expand_tabs": result=value.expandtabs(max(1,min(16,int(step.get("tabsize",4)))))
        elif action=="normalize_newlines": result=value.replace("\r\n","\n").replace("\r","\n")
        elif action=="remove_control_characters": result="".join(c for c in value if c in "\n\r\t" or unicodedata.category(c)!="Cc")
        elif action=="prefix_lines": result="\n".join(str(step.get("prefix",""))+x for x in lines)
        elif action=="suffix_lines": result="\n".join(x+str(step.get("suffix","")) for x in lines)
        elif action=="join_lines": result=str(step.get("separator"," ")).join(lines)
        elif action=="reverse_words": result=" ".join(reversed(value.split()))
        elif action=="split_words": return {"status":"succeeded","words":value.split()[:MAX_ITEMS],"count":len(value.split())}
        elif action=="alphabetize_words": result=" ".join(sorted(value.split(),key=str.casefold))
        elif action=="find_duplicate_words":
            counts=Counter(re.findall(r"\b[\w’'-]+\b",value.casefold()))
            return {"status":"succeeded","duplicates":[{"word":w,"count":n} for w,n in counts.items() if n>1][:MAX_ITEMS]}
        elif action=="find_long_words":
            n=step.get("min_length",8); n=n if isinstance(n,int) and 1<=n<=200 else 8
            result="\n".join(dict.fromkeys(w for w in re.findall(r"\b[\w’'-]+\b",value) if len(w)>=n))
        else:
            pat=step.get("pattern","")
            if not isinstance(pat,str) or len(pat)>300: return {"status":"failed","message":"Provide a regex pattern up to 300 characters."}
            try: rx=re.compile(pat)
            except re.error as exc: return {"status":"failed","message":"Invalid regex: "+str(exc)}
            result="\n".join(x for x in lines if bool(rx.search(x))==(action=="extract_lines_matching"))
        return {"status":"succeeded","text":result[:MAX_TEXT],"truncated":len(result)>MAX_TEXT}
    if action in {"html_escape","markdown_to_plain_text","markdown_to_html_safe","text_to_html_paragraphs","strip_xml_tags","extract_xml_attributes","extract_html_links","extract_css_urls","markdown_heading_slugs","generate_table_of_contents","extract_imports","strip_comments"}:
        if action=="html_escape": result=html.escape(value)
        elif action=="markdown_to_plain_text": result=re.sub(r"[*_>#~-]","",value)
        elif action=="strip_xml_tags": result=re.sub(r"<[^>]*>"," ",value)
        elif action in {"markdown_to_html_safe","text_to_html_paragraphs"}: result="\n".join("<p>"+html.escape(p)+"</p>" for p in re.split(r"\n\s*\n",value) if p.strip())
        elif action=="extract_xml_attributes": result=re.findall(r"""([A-Za-z_:][\w:.-]*)\s*=\s*["']([^"']*)["']""",value)
        elif action=="extract_html_links": result=re.findall(r"""(?is)<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""",value)
        elif action=="extract_css_urls": result=re.findall(r"""(?i)url\(\s*['"]?([^)'"]+)""",value)
        elif action=="markdown_heading_slugs": result=[re.sub(r"[^a-z0-9 -]","",x.lower()).strip().replace(" ","-") for x in re.findall(r"(?m)^#{1,6}\s+(.+)$",value)]
        elif action=="generate_table_of_contents":
            result="\n".join("- ["+title+"](#"+re.sub(r"[^a-z0-9 -]","",title.lower()).strip().replace(" ","-")+")" for _,title in re.findall(r"(?m)^(#{1,6})\s+(.+)$",value))
        elif action=="extract_imports": result=re.findall(r"(?m)^\s*(?:import\s+.+|from\s+\S+\s+import\s+.+)",value)
        else: result=re.sub(r"(?m)#.*$|//.*$|/\*.*?\*/","",value,flags=re.S)
        return {"status":"succeeded","result":result[:MAX_ITEMS] if isinstance(result,list) else result[:MAX_TEXT]}
    if action in {"json_keys","json_value_types","json_query","json_filter_array","json_sort_array","json_unique_array","json_to_csv","json_to_markdown_table","csv_to_json","csv_count_rows","csv_headers","csv_reverse_rows","csv_sample_rows","csv_deduplicate_rows","csv_select_columns","csv_column_rename","csv_column_remove","csv_filter_rows","csv_sort_rows","csv_rows_to_json","lines_to_json_array","key_value_to_json","json_to_key_value","parse_key_value_lines"}:
        if action=="lines_to_json_array": return {"status":"succeeded","json":json.dumps(lines,ensure_ascii=False)}
        if action in {"key_value_to_json","parse_key_value_lines"}:
            obj={}
            for line in lines:
                if "=" in line:
                    k,v=line.split("=",1)
                    if k.strip(): obj[k.strip()]=v.strip()
            return {"status":"succeeded","json":json.dumps(obj,ensure_ascii=False,indent=2),"values":obj}
        try: obj=json.loads(value)
        except json.JSONDecodeError as exc:
            if action=="json_to_key_value": return {"status":"failed","message":"Invalid JSON."}
            obj=None
        if action=="json_to_key_value":
            if not isinstance(obj,dict): return {"status":"failed","message":"JSON root must be an object."}
            return {"status":"succeeded","text":"\n".join(str(k)+"="+str(v) for k,v in obj.items())}
        if action.startswith("json_"):
            if action=="json_keys": return {"status":"succeeded","keys":list(obj.keys())[:MAX_ITEMS] if isinstance(obj,dict) else []}
            if action=="json_value_types":
                it=obj.items() if isinstance(obj,dict) else enumerate(obj) if isinstance(obj,list) else [("value",obj)]
                return {"status":"succeeded","types":{str(k):type(v).__name__ for k,v in list(it)[:MAX_ITEMS]}}
            if action=="json_query":
                current=obj
                try:
                    for p in str(step.get("path","")).strip(".").split("."):
                        if p: current=current[int(p)] if isinstance(current,list) else current[p]
                except (KeyError,IndexError,TypeError,ValueError): return {"status":"failed","message":"JSON path not found."}
                return {"status":"succeeded","value":current}
            if not isinstance(obj,list): return {"status":"failed","message":"JSON root must be an array."}
            if action=="json_filter_array": obj=[x for x in obj if isinstance(x,dict) and x.get(step.get("key"))==step.get("equals")]
            elif action=="json_sort_array": obj=sorted(obj,key=lambda x:str(x.get(step.get("key"),"")) if isinstance(x,dict) else str(x))
            elif action=="json_unique_array":
                seen=set(); unique=[]
                for x in obj:
                    token=json.dumps(x,sort_keys=True,ensure_ascii=False)
                    if token not in seen: seen.add(token);unique.append(x)
                obj=unique
            elif action=="json_to_csv":
                if not all(isinstance(x,dict) for x in obj): return {"status":"failed","message":"Expected an array of objects."}
                fields=list(dict.fromkeys(k for row in obj for k in row));out=io.StringIO();w=csv.DictWriter(out,fieldnames=fields);w.writeheader();w.writerows(obj[:5000])
                return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT]}
            elif action=="json_to_markdown_table":
                if not all(isinstance(x,dict) for x in obj): return {"status":"failed","message":"Expected an array of objects."}
                fields=list(dict.fromkeys(k for row in obj for k in row))
                return {"status":"succeeded","markdown":"| "+" | ".join(fields)+" |\n| "+" | ".join("---" for _ in fields)+" |\n"+"\n".join("| "+" | ".join(str(r.get(k,"")).replace("|","\\|") for k in fields)+" |" for r in obj[:5000])}
            return {"status":"succeeded","items":obj[:MAX_ITEMS],"count":len(obj)}
        if action.startswith("csv_"):
            try: rows=list(csv.DictReader(io.StringIO(value)))[:5000]
            except csv.Error as exc: return {"status":"failed","message":str(exc)}
            headers=list(rows[0].keys()) if rows else next(csv.reader(io.StringIO(value)),[])
            if action=="csv_count_rows": return {"status":"succeeded","row_count":len(rows)}
            if action=="csv_headers": return {"status":"succeeded","headers":headers}
            if action=="csv_select_columns":
                cols=step.get("columns",headers)
                if not isinstance(cols,list) or any(x not in headers for x in cols): return {"status":"failed","message":"Select existing column names."}
                headers=cols;rows=[{x:r.get(x,"") for x in cols} for r in rows]
            elif action=="csv_column_rename":
                col,new=step.get("column"),step.get("new_name")
                if col not in headers or not isinstance(new,str) or not new.strip(): return {"status":"failed","message":"Provide existing column and new_name."}
                headers=[new if h==col else h for h in headers];rows=[{new if k==col else k:v for k,v in r.items()} for r in rows]
            elif action=="csv_column_remove":
                col=step.get("column")
                if col not in headers: return {"status":"failed","message":"Column does not exist."}
                headers=[h for h in headers if h!=col];rows=[{k:v for k,v in r.items() if k!=col} for r in rows]
            elif action=="csv_filter_rows":
                col=step.get("column");needle=str(step.get("contains","")).casefold()
                if col not in headers: return {"status":"failed","message":"Column does not exist."}
                rows=[r for r in rows if needle in str(r.get(col,"")).casefold()]
            elif action=="csv_sort_rows":
                col=step.get("column")
                if col not in headers: return {"status":"failed","message":"Column does not exist."}
                rows.sort(key=lambda r:str(r.get(col,"")).casefold(),reverse=bool(step.get("descending",False)))
            elif action=="csv_deduplicate_rows":
                seen=set();unique=[]
                for r in rows:
                    key=json.dumps(r,sort_keys=True)
                    if key not in seen: seen.add(key);unique.append(r)
                rows=unique
            elif action=="csv_reverse_rows": rows.reverse()
            elif action=="csv_sample_rows":
                n=step.get("limit",10);n=n if isinstance(n,int) and 1<=n<=500 else 10;rows=rows[:n]
            elif action=="csv_rows_to_json": return {"status":"succeeded","json":json.dumps(rows,ensure_ascii=False,indent=2)[:MAX_TEXT]}
            out=io.StringIO();w=csv.DictWriter(out,fieldnames=headers);w.writeheader();w.writerows(rows)
            return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT],"row_count":len(rows)}
    if action in {"sum_numbers","average_numbers","median_numbers","min_max_numbers","numeric_summary","percent_change","calculate_percentage","calculate_discount","calculate_tax","calculate_simple_interest","calculate_compound_interest","calculate_loan_payment"}:
        nums=[float(x.replace(",","")) for x in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?",value)]
        if action=="percent_change":
            old=float(step.get("old",nums[0] if nums else 0));new=float(step.get("new",nums[1] if len(nums)>1 else 0))
            return {"status":"succeeded","percent_change":None if old==0 else (new-old)/abs(old)*100}
        if action.startswith("calculate_"):
            amount=float(step.get("amount",nums[0] if nums else 0));rate=float(step.get("rate",nums[1] if len(nums)>1 else 0))/100
            years=max(0,float(step.get("years",1)))
            if action=="calculate_percentage": result=amount*rate
            elif action=="calculate_discount": result=amount*(1-rate)
            elif action=="calculate_tax": result=amount*rate
            elif action=="calculate_simple_interest": result=amount*rate*years
            elif action=="calculate_compound_interest": result=amount*((1+rate)**years)-amount
            else:
                months=max(1,int(step.get("months",12)));monthly=rate/12
                result=amount*monthly/(1-(1+monthly)**(-months)) if monthly else amount/months
            return {"status":"succeeded","result":round(result,6)}
        if not nums: return {"status":"failed","message":"No numbers found."}
        if action=="sum_numbers": return {"status":"succeeded","sum":sum(nums)}
        if action=="average_numbers": return {"status":"succeeded","average":sum(nums)/len(nums)}
        if action=="median_numbers": return {"status":"succeeded","median":statistics.median(nums)}
        if action=="min_max_numbers": return {"status":"succeeded","minimum":min(nums),"maximum":max(nums)}
        return {"status":"succeeded","count":len(nums),"sum":sum(nums),"mean":statistics.mean(nums),"median":statistics.median(nums),"min":min(nums),"max":max(nums)}
    if action in {"validate_uuid","validate_ipv4","validate_email_list","generate_uuid","generate_timestamp","url_encode_text","url_decode_text","unicode_normalize","redact_urls","redact_ip_addresses","parse_iso_datetime","add_days","date_difference"}:
        if action=="validate_uuid": return {"status":"succeeded","valid":bool(re.fullmatch(r"(?i)[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",value.strip()))}
        if action=="validate_ipv4":
            p=value.strip().split(".");return {"status":"succeeded","valid":len(p)==4 and all(x.isdigit() and (x=="0" or not x.startswith("0")) and 0<=int(x)<=255 for x in p)}
        if action=="validate_email_list":
            items=[x.strip() for x in re.split(r"[,;\s]+",value) if x.strip()];valid=[x for x in items if re.fullmatch(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",x,re.I)]
            return {"status":"succeeded","valid":valid,"invalid":[x for x in items if x not in valid]}
        if action=="generate_uuid": return {"status":"succeeded","uuid":str(uuid.uuid4())}
        if action=="generate_timestamp": return {"status":"succeeded","timestamp":datetime.now(timezone.utc).isoformat()}
        if action=="url_encode_text": return {"status":"succeeded","text":quote(value,safe="")}
        if action=="url_decode_text": return {"status":"succeeded","text":unquote(value)}
        if action=="unicode_normalize":
            form=step.get("form","NFC")
            if form not in {"NFC","NFD","NFKC","NFKD"}: return {"status":"failed","message":"Invalid normalization form."}
            return {"status":"succeeded","text":unicodedata.normalize(form,value)}
        if action=="redact_urls": return {"status":"succeeded","text":re.sub(r"https?://\S+","[REDACTED_URL]",value)}
        if action=="redact_ip_addresses": return {"status":"succeeded","text":re.sub(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])","[REDACTED_IP]",value)}
        if action=="parse_iso_datetime":
            try: dt=datetime.fromisoformat(value.strip().replace("Z","+00:00"))
            except ValueError: return {"status":"failed","message":"Input must be ISO-8601 datetime."}
            return {"status":"succeeded","iso":dt.isoformat(),"unix_timestamp":dt.timestamp()}
        if action=="add_days":
            try: dt=datetime.fromisoformat(str(step.get("date",value)).replace("Z","+00:00"));days=int(step.get("days",0))
            except (ValueError,TypeError): return {"status":"failed","message":"Provide ISO date and integer days."}
            return {"status":"succeeded","result":(dt+timedelta(days=days)).isoformat()}
        try: start=datetime.fromisoformat(str(step.get("start_date","")).replace("Z","+00:00"));end=datetime.fromisoformat(str(step.get("end_date","")).replace("Z","+00:00"))
        except ValueError: return {"status":"failed","message":"Provide ISO start_date and end_date."}
        return {"status":"succeeded","days":(end-start).total_seconds()/86400}

    if action in {"format_json","json_to_yaml_preview","mask_text","count_occurrences","shuffle_preview","extract_log_levels","extract_sql_tables","extract_sql_statements","extract_json_paths","extract_csv_emails","count_sentiment_terms","readability_estimate","extract_acronyms","normalize_phone_candidates","extract_hex_colors","trim_lines","csv_to_markdown","extract_sql_columns","extract_sql_parameters","extract_api_endpoints"}:
        if action=="format_json":
            try: obj=json.loads(value)
            except json.JSONDecodeError as exc: return {"status":"failed","message":f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
            return {"status":"succeeded","json":json.dumps(obj,ensure_ascii=False,indent=2)[:MAX_TEXT]}
        if action=="json_to_yaml_preview":
            try: obj=json.loads(value)
            except json.JSONDecodeError: return {"status":"failed","message":"Invalid JSON."}
            def yaml_preview(item, depth=0):
                pad="  "*depth
                if isinstance(item,dict): return "\n".join(pad+str(k)+":"+(("\n"+yaml_preview(v,depth+1)) if isinstance(v,(dict,list)) else " "+json.dumps(v,ensure_ascii=False)) for k,v in item.items())
                if isinstance(item,list): return "\n".join(pad+"-"+(("\n"+yaml_preview(v,depth+1)) if isinstance(v,(dict,list)) else " "+json.dumps(v,ensure_ascii=False)) for v in item)
                return pad+json.dumps(item,ensure_ascii=False)
            return {"status":"succeeded","yaml_preview":yaml_preview(obj)[:MAX_TEXT],"note":"Simple YAML-like preview; verify compatibility before using as configuration."}
        if action=="mask_text":
            terms=step.get("terms",[])
            if not isinstance(terms,list) or any(not isinstance(x,str) for x in terms): return {"status":"failed","message":"terms must be a list of strings."}
            result=value
            for term in sorted((x for x in terms if x),key=len,reverse=True): result=re.sub(re.escape(term),str(step.get("replacement","[REDACTED]")),result,flags=re.I)
            return {"status":"succeeded","text":result[:MAX_TEXT]}
        if action=="count_occurrences":
            needle=step.get("needle","")
            if not isinstance(needle,str) or not needle: return {"status":"failed","message":"Provide a non-empty needle."}
            return {"status":"succeeded","count":value.count(needle),"case_insensitive_count":len(re.findall(re.escape(needle),value,re.I))}
        if action=="shuffle_preview":
            import random
            items=value.splitlines();seed=step.get("seed")
            random.Random(seed if isinstance(seed,(int,str)) else 0).shuffle(items)
            return {"status":"succeeded","lines":items[:MAX_ITEMS],"note":"Preview only; source content is not modified."}
        if action=="extract_log_levels":
            vals=re.findall(r"(?i)\b(DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b",value)
            return {"status":"succeeded","levels":[x.upper() for x in vals[:MAX_ITEMS]],"counts":dict(Counter(x.upper() for x in vals))}
        if action=="extract_sql_tables":
            vals=[]
            for pattern in (r"(?i)\bfrom\s+([A-Za-z_][\w.$]*)",r"(?i)\bjoin\s+([A-Za-z_][\w.$]*)",r"(?i)\bupdate\s+([A-Za-z_][\w.$]*)",r"(?i)\binsert\s+into\s+([A-Za-z_][\w.$]*)"): vals.extend(re.findall(pattern,value))
            return {"status":"succeeded","tables":list(dict.fromkeys(vals))[:MAX_ITEMS],"note":"Heuristic source parsing only; no query is executed."}
        if action=="extract_sql_statements":
            vals=[x.strip() for x in value.split(";") if x.strip()]
            return {"status":"succeeded","statements":vals[:MAX_ITEMS],"count":len(vals),"note":"Semicolon splitting is heuristic."}
        if action=="extract_json_paths":
            try: obj=json.loads(value)
            except json.JSONDecodeError: return {"status":"failed","message":"Invalid JSON."}
            paths=[]
            def walk(item,path="$"):
                if isinstance(item,dict):
                    for k,v in list(item.items())[:MAX_ITEMS]: paths.append(path+"."+str(k));walk(v,path+"."+str(k))
                elif isinstance(item,list):
                    for i,v in enumerate(item[:MAX_ITEMS]): paths.append(path+"["+str(i)+"]");walk(v,path+"["+str(i)+"]")
            walk(obj)
            return {"status":"succeeded","paths":paths[:MAX_ITEMS],"count":len(paths)}
        if action=="extract_csv_emails":
            vals=re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",value,re.I)
            return {"status":"succeeded","emails":list(dict.fromkeys(vals))[:MAX_ITEMS]}
        if action=="count_sentiment_terms":
            pos={"good","great","excellent","happy","love","wonderful","best","success","positive","enjoy"};neg={"bad","poor","terrible","sad","hate","awful","worst","fail","negative","angry"}
            words=[x.casefold() for x in re.findall(r"\b[\w'-]+\b",value)]
            p=sum(x in pos for x in words);n=sum(x in neg for x in words)
            return {"status":"succeeded","positive_terms":p,"negative_terms":n,"net":p-n,"note":"Simple keyword count, not a validated sentiment model."}
        if action=="readability_estimate":
            words=re.findall(r"\b[\w'-]+\b",value);sentences=[x for x in re.split(r"[.!?]+",value) if x.strip()]
            syllables=0
            for word in words:
                w=re.sub(r"[^a-z]","",word.lower());groups=len(re.findall(r"[aeiouy]+",w))
                syllables+=max(1,groups-int(w.endswith("e") and groups>1))
            if not words or not sentences: return {"status":"failed","message":"Provide text with sentence-ending punctuation."}
            score=206.835-1.015*(len(words)/len(sentences))-84.6*(syllables/len(words))
            return {"status":"succeeded","words":len(words),"sentences":len(sentences),"estimated_syllables":syllables,"flesch_reading_ease":round(score,2),"note":"Approximate English-language estimate."}
        if action=="extract_acronyms":
            vals=re.findall(r"\b[A-Z][A-Z0-9]{1,}s?\b",value)
            return {"status":"succeeded","acronyms":list(dict.fromkeys(vals))[:MAX_ITEMS]}
        if action=="normalize_phone_candidates":
            vals=re.findall(r"(?<!\w)\+?\d[\d ().-]{5,}\d(?!\w)",value)
            normalized=[("+" if x.strip().startswith("+") else "")+re.sub(r"\D","",x) for x in vals]
            return {"status":"succeeded","candidates":list(dict.fromkeys(normalized))[:MAX_ITEMS],"note":"Candidates are not validated against country numbering plans."}
        if action=="extract_hex_colors":
            vals=re.findall(r"(?i)#[0-9a-f]{3}(?:[0-9a-f]{3})?\b",value)
            return {"status":"succeeded","colors":list(dict.fromkeys(x.upper() for x in vals))[:MAX_ITEMS]}
        if action=="trim_lines": return {"status":"succeeded","text":"\n".join(x.strip() for x in lines)[:MAX_TEXT]}
        if action=="csv_to_markdown":
            try: rows=list(csv.reader(io.StringIO(value)))[:200]
            except csv.Error as exc: return {"status":"failed","message":str(exc)}
            if not rows: return {"status":"failed","message":"CSV is empty."}
            header=rows[0];result="| "+" | ".join(x.replace("|","\\|") for x in header)+" |\n| "+" | ".join("---" for _ in header)+" |\n"
            result+="\n".join("| "+" | ".join(x.replace("|","\\|") for x in row)+" |" for row in rows[1:])
            return {"status":"succeeded","markdown":result[:MAX_TEXT],"rows":len(rows)-1}
        if action=="extract_sql_columns":
            cols=[]
            for clause in re.findall(r"(?is)\bselect\s+(.*?)\s+from\b",value): cols.extend(x.strip().split()[-1].strip('"[]') for x in clause.split(",") if x.strip())
            return {"status":"succeeded","columns":list(dict.fromkeys(cols))[:MAX_ITEMS],"note":"Heuristic parser; SQL is not executed."}
        if action=="extract_sql_parameters":
            vals=re.findall(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)|(?<!%)%\(([A-Za-z_][A-Za-z0-9_]*)\)s",value)
            flat=[next((x for x in pair if x),"") for pair in vals]+re.findall(r"\$\d+",value)
            return {"status":"succeeded","parameters":list(dict.fromkeys(x for x in flat if x))[:MAX_ITEMS]}
        if action=="extract_api_endpoints":
            vals=re.findall(r"(?i)\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/[^\s\"'<>]+)",value)
            return {"status":"succeeded","endpoints":[{"method":m.upper(),"path":p} for m,p in vals[:MAX_ITEMS]]}

    if action in {"extract_words","extract_unique_words","word_count_by_paragraph","sentence_count","count_punctuation","count_uppercase","count_digits","strip_accents","transliterate_ascii","mask_digits","mask_emails","mask_phone_numbers","mask_credit_card_candidates","extract_email_domains","extract_urls_with_paths","extract_query_params","url_join_preview","format_json_compact","json_merge_objects","json_array_unique","json_array_length","csv_filter_by_value","csv_rename_header","csv_column_summary","csv_quote_values","csv_to_html_table","html_table_to_csv","extract_markdown_code_languages","extract_markdown_links_and_images","extract_html_headings","extract_html_emails","extract_css_colors","extract_git_hashes","extract_semver_versions","extract_ipv6_candidates","extract_mac_addresses","extract_port_numbers","parse_ini_preview","parse_env_preview","parse_log_timestamps","count_log_levels","extract_error_lines","extract_hex_colors"}:
        if action=="extract_words":
            vals=re.findall(r"[\w’'-]+",value,re.UNICODE)
            return {"status":"succeeded","words":vals[:MAX_ITEMS],"count":len(vals)}
        if action=="extract_unique_words":
            vals=list(dict.fromkeys(x.casefold() for x in re.findall(r"[\w’'-]+",value,re.UNICODE)))
            return {"status":"succeeded","words":vals[:MAX_ITEMS],"count":len(vals)}
        if action=="word_count_by_paragraph":
            vals=[p for p in re.split(r"\n\s*\n",value.strip()) if p.strip()]
            return {"status":"succeeded","paragraphs":[{"index":i,"word_count":len(p.split())} for i,p in enumerate(vals[:MAX_ITEMS],1)],"count":len(vals)}
        if action=="sentence_count": return {"status":"succeeded","sentence_count":len([x for x in re.split(r"(?<=[.!?])\s+",value.strip()) if x])}
        if action=="count_punctuation":
            vals=Counter(ch for ch in value if unicodedata.category(ch).startswith("P"))
            return {"status":"succeeded","punctuation_count":sum(vals.values()),"counts":dict(vals.most_common(100))}
        if action=="count_uppercase": return {"status":"succeeded","uppercase_characters":sum(x.isupper() for x in value),"lowercase_characters":sum(x.islower() for x in value)}
        if action=="count_digits": return {"status":"succeeded","digit_count":sum(x.isdigit() for x in value),"digits":re.findall(r"\d",value)[:MAX_ITEMS]}
        if action in {"strip_accents","transliterate_ascii"}:
            result="".join(x for x in unicodedata.normalize("NFKD",value) if not unicodedata.combining(x))
            if action=="transliterate_ascii": result=result.encode("ascii","ignore").decode("ascii")
            return {"status":"succeeded","text":result[:MAX_TEXT]}
        if action=="mask_digits": return {"status":"succeeded","text":re.sub(r"\d","*",value)}
        if action=="mask_emails": return {"status":"succeeded","text":re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}","[REDACTED_EMAIL]",value,flags=re.I)}
        if action=="mask_phone_numbers": return {"status":"succeeded","text":re.sub(r"(?<!\w)\+?\d[\d ().-]{5,}\d(?!\w)","[REDACTED_PHONE]",value)}
        if action=="mask_credit_card_candidates": return {"status":"succeeded","text":re.sub(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)","[REDACTED_CARD_CANDIDATE]",value),"note":"Pattern-based masking only; no card validity check."}
        if action=="extract_email_domains":
            vals=re.findall(r"[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})",value,re.I)
            return {"status":"succeeded","domains":list(dict.fromkeys(x.lower() for x in vals))[:MAX_ITEMS]}
        if action in {"extract_urls_with_paths","extract_query_params","url_join_preview"}:
            if action=="url_join_preview":
                from urllib.parse import urljoin
                base=step.get("base_url","");parsed=urlparse(base)
                if not isinstance(base,str) or parsed.scheme not in {"http","https"} or not parsed.hostname: return {"status":"failed","message":"base_url must be an absolute HTTP/HTTPS URL."}
                return {"status":"succeeded","url":urljoin(base,value.strip())[:4000],"network_access":False}
            urls=re.findall(r"https?://[^\s<>\"']+",value,re.I);results=[]
            from urllib.parse import parse_qs
            for url in urls:
                p=urlparse(url)
                if not p.hostname: continue
                results.append({"url":url,"host":p.hostname,"path":p.path,"query":parse_qs(p.query) if action=="extract_query_params" else p.query})
            return {"status":"succeeded","urls":results[:MAX_ITEMS]}
        if action in {"format_json_compact","json_merge_objects","json_array_unique","json_array_length"}:
            try: obj=json.loads(value)
            except json.JSONDecodeError as exc: return {"status":"failed","message":f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
            if action=="json_merge_objects":
                raw=step.get("second_input","")
                try: second=json.loads(raw) if isinstance(raw,str) else raw
                except json.JSONDecodeError: return {"status":"failed","message":"second_input must be valid JSON."}
                if not isinstance(obj,dict) or not isinstance(second,dict): return {"status":"failed","message":"Both JSON values must be objects."}
                obj={**obj,**second}
            elif action in {"json_array_unique","json_array_length"}:
                if not isinstance(obj,list): return {"status":"failed","message":"JSON root must be an array."}
                if action=="json_array_length": return {"status":"succeeded","length":len(obj)}
                seen=set();unique=[]
                for item in obj:
                    key=json.dumps(item,sort_keys=True,ensure_ascii=False)
                    if key not in seen: seen.add(key);unique.append(item)
                obj=unique
            result=json.dumps(obj,ensure_ascii=False,separators=(",",":") if action=="format_json_compact" else (",",": "))
            return {"status":"succeeded","json":result[:MAX_TEXT],"truncated":len(result)>MAX_TEXT}
        if action in {"csv_filter_by_value","csv_rename_header","csv_column_summary","csv_quote_values","csv_to_html_table","html_table_to_csv"}:
            if action=="html_table_to_csv":
                table=re.search(r"(?is)<table\b.*?</table\s*>",value)
                if not table:return {"status":"failed","message":"No HTML table found."}
                rows=[]
                for row in re.findall(r"(?is)<tr\b.*?</tr\s*>",table.group(0)):
                    cells=re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]\s*>",row)
                    rows.append([re.sub(r"<[^>]*>","",x).strip() for x in cells])
                out=io.StringIO();csv.writer(out).writerows(rows[:MAX_ITEMS])
                return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT],"row_count":len(rows)}
            try: rows=list(csv.DictReader(io.StringIO(value)))[:5000]
            except csv.Error as exc:return {"status":"failed","message":str(exc)}
            if not rows:return {"status":"failed","message":"CSV needs a header and at least one data row."}
            headers=list(rows[0].keys())
            if action=="csv_filter_by_value":
                col=step.get("column");needle=str(step.get("contains","")).casefold()
                if col not in headers:return {"status":"failed","message":"Column does not exist."}
                rows=[r for r in rows if needle in str(r.get(col,"")).casefold()]
            elif action=="csv_rename_header":
                col,new=step.get("column"),step.get("new_name")
                if col not in headers or not isinstance(new,str) or not new.strip() or (new in headers and new!=col):return {"status":"failed","message":"Provide an existing column and unique new_name."}
                headers=[new if x==col else x for x in headers];rows=[{new if k==col else k:v for k,v in r.items()} for r in rows]
            elif action=="csv_column_summary":
                col=step.get("column")
                if col not in headers:return {"status":"failed","message":"Column does not exist."}
                vals=[str(r.get(col,"") or "") for r in rows]
                return {"status":"succeeded","column":col,"non_empty":sum(bool(x.strip()) for x in vals),"unique_count":len(set(vals)),"sample_values":list(dict.fromkeys(vals))[:20]}
            if action=="csv_to_html_table":
                esc=lambda x:html.escape(str(x or ""))
                result="<table><thead><tr>"+"".join("<th>"+esc(x)+"</th>" for x in headers)+"</tr></thead><tbody>"+"".join("<tr>"+"".join("<td>"+esc(r.get(x,""))+"</td>" for x in headers)+"</tr>" for r in rows[:200])+"</tbody></table>"
                return {"status":"succeeded","html":result[:MAX_TEXT],"row_count":len(rows)}
            out=io.StringIO();writer=csv.DictWriter(out,fieldnames=headers,quoting=csv.QUOTE_ALL if action=="csv_quote_values" else csv.QUOTE_MINIMAL);writer.writeheader();writer.writerows(rows)
            return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT],"row_count":len(rows)}
        if action=="extract_markdown_code_languages":
            vals=re.findall(r"(?m)^\s*"+chr(96)*3+r"([^\s"+chr(96)+r"]*)",value)
            return {"status":"succeeded","languages":list(dict.fromkeys(x or "unspecified" for x in vals))[:MAX_ITEMS]}
        if action=="extract_markdown_links_and_images":
            links=[{"type":"link","label":a,"url":b} for a,b in re.findall(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)",value)]
            links.extend({"type":"image","label":a,"url":b} for a,b in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)",value))
            return {"status":"succeeded","items":links[:MAX_ITEMS],"count":len(links)}
        if action=="extract_html_headings":
            vals=[{"level":int(a),"text":re.sub(r"<[^>]*>","",b).strip()} for a,b in re.findall(r"(?is)<h([1-6])\b[^>]*>(.*?)</h[1-6]\s*>",value)]
            return {"status":"succeeded","headings":vals[:MAX_ITEMS],"count":len(vals)}
        if action=="extract_html_emails":
            vals=re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",re.sub(r"<[^>]*>"," ",value),re.I)
            return {"status":"succeeded","emails":list(dict.fromkeys(vals))[:MAX_ITEMS]}
        if action in {"extract_css_colors","extract_hex_colors"}:
            vals=re.findall(r"(?i)#[0-9a-f]{3}(?:[0-9a-f]{3})?\b|rgba?\([^)]*\)|hsla?\([^)]*\)",value)
            return {"status":"succeeded","colors":list(dict.fromkeys(x.upper() if x.startswith("#") else x for x in vals))[:MAX_ITEMS]}
        if action=="extract_git_hashes":
            vals=re.findall(r"(?i)\b(?:[0-9a-f]{40}|[0-9a-f]{64})\b",value)
            return {"status":"succeeded","hashes":list(dict.fromkeys(vals))[:MAX_ITEMS]}
        if action=="extract_semver_versions":
            vals=re.findall(r"(?<![\w])v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",value)
            return {"status":"succeeded","versions":list(dict.fromkeys(vals))[:MAX_ITEMS]}
        if action=="extract_ipv6_candidates":
            vals=re.findall(r"(?i)(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])",value)
            return {"status":"succeeded","candidates":list(dict.fromkeys(vals))[:MAX_ITEMS],"note":"Candidates are not fully validated IPv6 addresses."}
        if action=="extract_mac_addresses":
            vals=re.findall(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b",value)
            return {"status":"succeeded","addresses":list(dict.fromkeys(x.upper().replace("-",":") for x in vals))[:MAX_ITEMS]}
        if action=="extract_port_numbers":
            vals=[int(x) for x in re.findall(r"(?i)\bport\s*[:=]?\s*(\d{1,5})\b",value) if 1<=int(x)<=65535]
            return {"status":"succeeded","ports":list(dict.fromkeys(vals))[:MAX_ITEMS]}
        if action in {"parse_ini_preview","parse_env_preview"}:
            result={}
            for line in value.splitlines():
                line=line.strip()
                if not line or line.startswith(("#",";")) or (action=="parse_ini_preview" and line.startswith("[")):continue
                if "=" in line:
                    k,v=line.split("=",1);k=k.strip()
                    if k and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*",k):result[k]=v.strip().strip('"').strip("'")
            return {"status":"succeeded","values":dict(list(result.items())[:MAX_ITEMS]),"count":len(result),"note":"Preview only; no environment or app settings are changed."}
        if action=="parse_log_timestamps":
            vals=re.findall(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",value)
            return {"status":"succeeded","timestamps":list(dict.fromkeys(vals))[:MAX_ITEMS]}
        if action in {"count_log_levels","extract_error_lines"}:
            if action=="count_log_levels":
                vals=re.findall(r"(?i)\b(DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b",value)
                return {"status":"succeeded","counts":dict(Counter(x.upper() for x in vals)),"total_matches":len(vals)}
            vals=[x for x in lines if re.search(r"(?i)\b(ERROR|CRITICAL|FATAL|EXCEPTION|TRACEBACK)\b",x)]
            return {"status":"succeeded","lines":vals[:MAX_ITEMS],"count":len(vals),"truncated":len(vals)>MAX_ITEMS}

    if action in {"json_flatten","json_deep_merge","json_path_values","json_array_flatten","json_array_reverse","json_array_sort","sort_json_keys","json_pretty_print","json_compact_print","extract_json_objects","markdown_table_to_json","json_to_markdown_list"}:
        try: obj=json.loads(value)
        except json.JSONDecodeError as exc: return {"status":"failed","message":f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        if action=="json_deep_merge":
            raw=step.get("second_input","")
            try: other=json.loads(raw) if isinstance(raw,str) else raw
            except json.JSONDecodeError:return {"status":"failed","message":"second_input must be valid JSON."}
            def merge(a,b):
                if isinstance(a,dict) and isinstance(b,dict):
                    out=dict(a)
                    for k,v in b.items():out[k]=merge(out[k],v) if k in out else v
                    return out
                return b
            if not isinstance(obj,dict) or not isinstance(other,dict):return {"status":"failed","message":"Both values must be JSON objects."}
            obj=merge(obj,other)
        if action=="json_flatten":
            flat={}
            def flatten(v,prefix="$"):
                if isinstance(v,dict):
                    for k,x in v.items():flatten(x,prefix+"."+str(k))
                elif isinstance(v,list):
                    for i,x in enumerate(v):flatten(x,prefix+"["+str(i)+"]")
                else:flat[prefix]=v
            flatten(obj);return {"status":"succeeded","values":dict(list(flat.items())[:MAX_ITEMS]),"count":len(flat)}
        if action=="json_path_values":
            paths=[]
            def paths_walk(v,p="$"):
                paths.append({"path":p,"type":type(v).__name__,"value":v if not isinstance(v,(dict,list)) else None})
                if isinstance(v,dict):
                    for k,x in list(v.items())[:MAX_ITEMS]:paths_walk(x,p+"."+str(k))
                elif isinstance(v,list):
                    for i,x in enumerate(v[:MAX_ITEMS]):paths_walk(x,p+"["+str(i)+"]")
            paths_walk(obj);return {"status":"succeeded","paths":paths[:MAX_ITEMS],"count":len(paths)}
        if action=="json_array_flatten":
            if not isinstance(obj,list):return {"status":"failed","message":"JSON root must be an array."}
            flat=[]
            def flatten_array(v):
                for x in v:
                    flatten_array(x) if isinstance(x,list) else flat.append(x)
            flatten_array(obj);return {"status":"succeeded","items":flat[:MAX_ITEMS],"count":len(flat)}
        if action in {"json_array_reverse","json_array_sort","json_array_flatten"}:
            if not isinstance(obj,list):return {"status":"failed","message":"JSON root must be an array."}
            if action=="json_array_reverse":obj.reverse()
            elif action=="json_array_sort":obj=sorted(obj,key=lambda x:str(x).casefold(),reverse=bool(step.get("descending",False)))
            return {"status":"succeeded","items":obj[:MAX_ITEMS],"count":len(obj)}
        if action=="sort_json_keys":
            return {"status":"succeeded","json":json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)[:MAX_TEXT]}
        if action=="json_pretty_print":return {"status":"succeeded","json":json.dumps(obj,ensure_ascii=False,indent=2)[:MAX_TEXT]}
        if action=="json_compact_print":return {"status":"succeeded","json":json.dumps(obj,ensure_ascii=False,separators=(",",":"))[:MAX_TEXT]}
        if action=="extract_json_objects":
            vals=[]
            for match in re.finditer(r"\{(?:[^{}]|(?R))*\}",value): vals.append(match.group(0))
            return {"status":"succeeded","objects":vals[:MAX_ITEMS],"count":len(vals),"note":"Nested object extraction is best-effort and does not use recursive regex features."}
        if action=="markdown_table_to_json":
            rows=[]
            for line in value.splitlines():
                if line.strip().startswith("|") and not re.match(r"^\s*\|?[-:| ]+\|?\s*$",line):
                    rows.append([x.strip() for x in line.strip().strip("|").split("|")])
            if len(rows)<2:return {"status":"failed","message":"No Markdown table with header and data rows found."}
            headers=rows[0];items=[dict(zip(headers,row)) for row in rows[1:] if len(row)==len(headers)]
            return {"status":"succeeded","json":json.dumps(items[:MAX_ITEMS],ensure_ascii=False,indent=2)[:MAX_TEXT],"rows":len(items)}
        if action=="json_to_markdown_list":
            items=obj if isinstance(obj,list) else list(obj.items()) if isinstance(obj,dict) else [obj]
            return {"status":"succeeded","markdown":"\n".join("- "+json.dumps(x,ensure_ascii=False) for x in items[:MAX_ITEMS])[:MAX_TEXT]}
    if action in {"csv_to_xml_preview","csv_column_sum","csv_column_average","csv_column_min_max","csv_transpose","csv_group_count","csv_find_duplicates","csv_remove_duplicates","csv_to_sql_inserts_preview","csv_column_median","csv_column_frequency","csv_validate_email_column","csv_validate_numbers"}:
        try: rows=list(csv.DictReader(io.StringIO(value)))[:5000]
        except csv.Error as exc:return {"status":"failed","message":str(exc)}
        headers=list(rows[0].keys()) if rows else next(csv.reader(io.StringIO(value)),[])
        if not headers:return {"status":"failed","message":"CSV must have a header row."}
        col=step.get("column")
        if action in {"csv_column_sum","csv_column_average","csv_column_min_max","csv_column_median","csv_column_frequency","csv_validate_email_column","csv_validate_numbers"}:
            if col not in headers:return {"status":"failed","message":"Provide an existing column name."}
            vals=[str(r.get(col,"") or "") for r in rows]
            if action=="csv_column_frequency":
                counts=Counter(vals);return {"status":"succeeded","column":col,"frequencies":dict(counts.most_common(MAX_ITEMS))}
            if action=="csv_validate_email_column":
                valid=[x for x in vals if re.fullmatch(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",x,re.I)]
                return {"status":"succeeded","column":col,"valid_count":len(valid),"invalid_values":[x for x in vals if x and x not in valid][:MAX_ITEMS]}
            if action=="csv_validate_numbers":
                good=[]
                for x in vals:
                    try:good.append(float(x.replace(",","")))
                    except ValueError:pass
                return {"status":"succeeded","column":col,"valid_count":len(good),"invalid_values":[x for x in vals if x and not re.fullmatch(r"-?\d+(?:\.\d+)?",x.replace(",",""))][:MAX_ITEMS]}
            nums=[]
            for x in vals:
                try:nums.append(float(x.replace(",","")))
                except ValueError:pass
            if not nums:return {"status":"failed","message":"Column contains no numeric values."}
            if action=="csv_column_sum":result=sum(nums)
            elif action=="csv_column_average":result=sum(nums)/len(nums)
            elif action=="csv_column_min_max":return {"status":"succeeded","minimum":min(nums),"maximum":max(nums),"count":len(nums)}
            elif action=="csv_column_median":result=statistics.median(nums)
            return {"status":"succeeded","column":col,"result":result,"count":len(nums)}
        if action=="csv_transpose":
            matrix=[headers]+[[r.get(h,"") for h in headers] for r in rows]
            out=io.StringIO();csv.writer(out).writerows(list(map(list,zip(*matrix))) if matrix else [])
            return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT]}
        if action=="csv_group_count":
            if col not in headers:return {"status":"failed","message":"Provide an existing column name."}
            return {"status":"succeeded","counts":dict(Counter(str(r.get(col,"")) for r in rows).most_common(MAX_ITEMS))}
        if action in {"csv_find_duplicates","csv_remove_duplicates"}:
            seen=set();dups=[];unique=[]
            for r in rows:
                key=json.dumps(r,sort_keys=True)
                if key in seen:dups.append(r)
                else:seen.add(key);unique.append(r)
            if action=="csv_find_duplicates":return {"status":"succeeded","duplicates":dups[:MAX_ITEMS],"count":len(dups)}
            rows=unique
        if action=="csv_to_sql_inserts_preview":
            table=step.get("table","records")
            if not isinstance(table,str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",table):return {"status":"failed","message":"table must be a simple SQL identifier."}
            def sqlq(x):return "NULL" if x is None or x=="" else "'"+str(x).replace("'","''")+"'"
            statements=["INSERT INTO "+table+" ("+", ".join(headers)+") VALUES ("+", ".join(sqlq(r.get(h,"")) for h in headers)+");" for r in rows[:100]]
            return {"status":"succeeded","sql_preview":"\n".join(statements)[:MAX_TEXT],"count":len(statements),"note":"Preview only; SQL is not executed."}
        if action=="csv_to_xml_preview":
            esc=lambda x:html.escape(str(x or ""))
            xml="<rows>"+"".join("<row>"+"".join("<"+re.sub(r"[^A-Za-z0-9_-]","_",h)+">"+esc(r.get(h,""))+"</"+re.sub(r"[^A-Za-z0-9_-]","_",h)+">" for h in headers)+"</row>" for r in rows[:200])+"</rows>"
            return {"status":"succeeded","xml_preview":xml[:MAX_TEXT],"rows":len(rows)}
    if action in {"count_word_lengths","word_length_histogram","sentence_case","title_case","camel_case","pascal_case","snake_case","kebab_case","extract_lines_unique","compare_lists","extract_semver","extract_uuids","extract_hex_numbers","extract_markdown_headings","extract_html_title","extract_html_meta","extract_html_links_text","extract_python_classes","extract_python_imports","extract_javascript_functions"}:
        if action=="count_word_lengths" or action=="word_length_histogram":
            counts=Counter(len(x) for x in re.findall(r"\b[\w'-]+\b",value))
            return {"status":"succeeded","histogram":dict(sorted(counts.items())),"word_count":sum(counts.values())}
        if action in {"sentence_case","title_case","camel_case","pascal_case","snake_case","kebab_case"}:
            words=re.findall(r"[A-Za-z0-9]+",value)
            if action=="sentence_case":result=value[:1].upper()+value[1:].lower()
            elif action=="title_case":result=" ".join(x[:1].upper()+x[1:].lower() for x in words)
            elif action=="camel_case":result="".join([words[0].lower()]+[x.title() for x in words[1:]]) if words else ""
            elif action=="pascal_case":result="".join(x.title() for x in words)
            elif action=="snake_case":result="_".join(x.lower() for x in words)
            else:result="-".join(x.lower() for x in words)
            return {"status":"succeeded","text":result}
        if action=="extract_lines_unique":
            unique=list(dict.fromkeys(lines));return {"status":"succeeded","lines":unique[:MAX_ITEMS],"count":len(unique)}
        if action=="compare_lists":
            other=step.get("second_input","")
            if not isinstance(other,str):return {"status":"failed","message":"second_input must be text."}
            left=set(x.strip() for x in value.splitlines() if x.strip());right=set(x.strip() for x in other.splitlines() if x.strip())
            return {"status":"succeeded","common":sorted(left&right)[:MAX_ITEMS],"only_first":sorted(left-right)[:MAX_ITEMS],"only_second":sorted(right-left)[:MAX_ITEMS]}
        if action in {"extract_semver","extract_uuids","extract_hex_numbers"}:
            pat={"extract_semver":r"(?<![\w])v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?","extract_uuids":r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b","extract_hex_numbers":r"(?i)\b0x[0-9a-f]+\b"}[action]
            vals=list(dict.fromkeys(re.findall(pat,value)));return {"status":"succeeded","items":vals[:MAX_ITEMS],"count":len(vals)}
        if action=="extract_markdown_headings":
            vals=[{"level":len(a),"text":b.strip()} for a,b in re.findall(r"(?m)^(#{1,6})\s+(.+)$",value)]
            return {"status":"succeeded","headings":vals[:MAX_ITEMS]}
        if action=="extract_html_title":
            m=re.search(r"(?is)<title\b[^>]*>(.*?)</title\s*>",value)
            return {"status":"succeeded","title":re.sub(r"<[^>]*>","",m.group(1)).strip() if m else ""}
        if action=="extract_html_meta":
            vals=re.findall(r"""(?is)<meta\b[^>]*(?:name|property)=["']([^"']+)["'][^>]*content=["']([^"']*)["'][^>]*>""",value)
            return {"status":"succeeded","metadata":[{"name":a,"content":b} for a,b in vals[:MAX_ITEMS]]}
        if action=="extract_html_links_text":
            vals=re.findall(r"(?is)<a\b[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>",value)
            return {"status":"succeeded","links":[{"url":a,"text":re.sub(r"<[^>]*>","",b).strip()} for a,b in vals[:MAX_ITEMS]]}
        if action in {"extract_python_classes","extract_python_imports"}:
            pat=r"(?m)^\s*class\s+([A-Za-z_]\w*)" if action=="extract_python_classes" else r"(?m)^\s*(?:from\s+\S+\s+import\s+.+|import\s+.+)"
            return {"status":"succeeded","items":re.findall(pat,value)[:MAX_ITEMS]}
        vals=re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(",value)
        return {"status":"succeeded","functions":[next((x for x in pair if x),"") for pair in vals[:MAX_ITEMS]]}
    if action in {"normalize_unicode_nfc","normalize_unicode_nfkc"}:
        form="NFC" if action=="normalize_unicode_nfc" else "NFKC"
        return {"status":"succeeded","text":unicodedata.normalize(form,value)}
    if action=="mask_custom_pattern":
        pattern=step.get("pattern","")
        if not isinstance(pattern,str) or not pattern or len(pattern)>300:return {"status":"failed","message":"Provide a non-empty regex pattern up to 300 characters."}
        try:rx=re.compile(pattern)
        except re.error as exc:return {"status":"failed","message":"Invalid regex: "+str(exc)}
        return {"status":"succeeded","text":rx.sub(str(step.get("replacement","[REDACTED]")),value)[:MAX_TEXT]}
    if action in {"business_days_between","add_business_days","is_leap_year","days_in_month","age_from_date","format_datetime","convert_timezone"}:
        from calendar import isleap, monthrange
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        if action=="is_leap_year":
            try:y=int(step.get("year",value.strip()))
            except ValueError:return {"status":"failed","message":"Provide a year."}
            return {"status":"succeeded","year":y,"is_leap_year":isleap(y)}
        if action=="days_in_month":
            try:y=int(step.get("year"));m=int(step.get("month"))
            except (TypeError,ValueError):return {"status":"failed","message":"Provide year and month."}
            if not 1<=m<=12:return {"status":"failed","message":"month must be 1–12."}
            return {"status":"succeeded","days":monthrange(y,m)[1]}
        if action=="age_from_date":
            try:birth=datetime.fromisoformat(str(step.get("birth_date",value)).replace("Z","+00:00")).date()
            except ValueError:return {"status":"failed","message":"Provide birth_date in ISO format."}
            today=datetime.now(timezone.utc).date();return {"status":"succeeded","years":today.year-birth.year-((today.month,today.day)<(birth.month,birth.day))}
        if action=="format_datetime":
            try:dt=datetime.fromisoformat(str(step.get("datetime",value)).replace("Z","+00:00"))
            except ValueError:return {"status":"failed","message":"Provide ISO datetime."}
            fmt=step.get("format","%Y-%m-%d %H:%M:%S")
            if not isinstance(fmt,str) or len(fmt)>100:return {"status":"failed","message":"Invalid format string."}
            return {"status":"succeeded","formatted":dt.strftime(fmt)}
        if action=="convert_timezone":
            try:dt=datetime.fromisoformat(str(step.get("datetime",value)).replace("Z","+00:00"));zone=ZoneInfo(str(step.get("timezone","UTC")))
            except (ValueError,ZoneInfoNotFoundError):return {"status":"failed","message":"Provide ISO datetime and valid IANA timezone."}
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            return {"status":"succeeded","datetime":dt.astimezone(zone).isoformat(),"timezone":str(zone)}
        if action=="add_business_days":
            try:dt=datetime.fromisoformat(str(step.get("date",value)).replace("Z","+00:00"));n=int(step.get("days",0))
            except (ValueError,TypeError):return {"status":"failed","message":"Provide date and integer days."}
            direction=1 if n>=0 else -1
            for _ in range(min(abs(n),10000)):
                dt+=timedelta(days=direction)
                if dt.weekday()<5: n-=direction
            return {"status":"succeeded","date":dt.date().isoformat()}
        try:a=datetime.fromisoformat(str(step.get("start_date","")).replace("Z","+00:00")).date();b=datetime.fromisoformat(str(step.get("end_date","")).replace("Z","+00:00")).date()
        except ValueError:return {"status":"failed","message":"Provide ISO start_date and end_date."}
        lo,hi=sorted((a,b));days=sum(1 for i in range((hi-lo).days) if (lo+timedelta(days=i)).weekday()<5)
        return {"status":"succeeded","business_days":days if b>=a else -days}

    if action in {"json_merge_arrays","json_array_filter_contains","json_array_slice","json_object_pick","json_object_omit","json_object_rename_key","json_object_remove_key","json_object_get","json_object_set","json_object_to_pairs","json_pairs_to_object","json_escape_string","json_unescape_string","json_count_nodes","json_max_depth","json_extract_strings","json_extract_numbers","json_extract_booleans","json_extract_nulls","jsonl_to_json","json_to_jsonl","json_flatten","json_deep_merge","json_path_values","json_array_flatten","json_array_reverse","json_array_sort","sort_json_keys","json_pretty_print","json_compact_print"}:
        if action=="json_escape_string": return {"status":"succeeded","json_string":json.dumps(value,ensure_ascii=False)}
        if action in {"jsonl_to_json","json_to_jsonl"}:
            if action=="jsonl_to_json":
                vals=[]
                for i,line in enumerate(lines,1):
                    if line.strip():
                        try:vals.append(json.loads(line))
                        except json.JSONDecodeError:return {"status":"failed","message":"Invalid JSON on line "+str(i)}
                return {"status":"succeeded","json":json.dumps(vals,ensure_ascii=False,indent=2)[:MAX_TEXT]}
            try:obj=json.loads(value)
            except json.JSONDecodeError:return {"status":"failed","message":"Invalid JSON."}
            return {"status":"succeeded","jsonl":"\n".join(json.dumps(x,ensure_ascii=False,separators=(",",":")) for x in (obj if isinstance(obj,list) else [obj])[:MAX_ITEMS])}
        if action=="json_unescape_string":
            try:obj=json.loads(value)
            except json.JSONDecodeError:return {"status":"failed","message":"Input must be a JSON string literal."}
            return {"status":"succeeded","text":obj} if isinstance(obj,str) else {"status":"failed","message":"JSON value must be a string."}
        try:obj=json.loads(value)
        except json.JSONDecodeError as exc:return {"status":"failed","message":f"Invalid JSON at line {exc.lineno}, column {exc.colno}."}
        if action=="json_deep_merge":
            raw=step.get("second_input","")
            try:other=json.loads(raw) if isinstance(raw,str) else raw
            except json.JSONDecodeError:return {"status":"failed","message":"second_input must be valid JSON."}
            if not isinstance(obj,dict) or not isinstance(other,dict):return {"status":"failed","message":"Both values must be objects."}
            def deep_merge(a,b):
                if isinstance(a,dict) and isinstance(b,dict):
                    out=dict(a)
                    for k,v in b.items():out[k]=deep_merge(out[k],v) if k in out else v
                    return out
                return b
            obj=deep_merge(obj,other)
        if action=="json_merge_arrays":
            raw=step.get("second_input","")
            try:other=json.loads(raw) if isinstance(raw,str) else raw
            except json.JSONDecodeError:return {"status":"failed","message":"second_input must be valid JSON."}
            if not isinstance(obj,list) or not isinstance(other,list):return {"status":"failed","message":"Both values must be arrays."}
            return {"status":"succeeded","items":(obj+other)[:MAX_ITEMS],"count":len(obj)+len(other)}
        if action in {"json_object_pick","json_object_omit","json_object_rename_key","json_object_remove_key","json_object_get","json_object_set","json_object_to_pairs"}:
            if not isinstance(obj,dict):return {"status":"failed","message":"JSON root must be an object."}
            key=step.get("key")
            if action=="json_object_pick":
                keys=step.get("keys",[]);return {"status":"succeeded","object":{k:obj[k] for k in keys if k in obj}}
            if action=="json_object_omit":
                keys=step.get("keys",[]);return {"status":"succeeded","object":{k:v for k,v in obj.items() if k not in keys}}
            if action=="json_object_rename_key":
                new=step.get("new_key")
                if key not in obj or not isinstance(new,str) or not new.strip():return {"status":"failed","message":"Provide existing key and new_key."}
                obj[new]=obj.pop(key);return {"status":"succeeded","object":obj}
            if action=="json_object_remove_key":
                if key not in obj:return {"status":"failed","message":"Key not found."}
                obj.pop(key);return {"status":"succeeded","object":obj}
            if action=="json_object_get":
                if key not in obj:return {"status":"failed","message":"Key not found."}
                return {"status":"succeeded","value":obj[key]}
            if action=="json_object_set":obj[key]=step.get("value");return {"status":"succeeded","object":obj}
            return {"status":"succeeded","pairs":[{"key":k,"value":v} for k,v in list(obj.items())[:MAX_ITEMS]]}
        if action=="json_pairs_to_object":
            if not isinstance(obj,list):return {"status":"failed","message":"JSON root must be an array."}
            return {"status":"succeeded","object":{str(x["key"]):x["value"] for x in obj if isinstance(x,dict) and "key" in x and "value" in x}}
        if action in {"json_array_filter_contains","json_array_slice","json_array_flatten","json_array_reverse","json_array_sort"}:
            if not isinstance(obj,list):return {"status":"failed","message":"JSON root must be an array."}
            if action=="json_array_filter_contains":obj=[x for x in obj if str(step.get("contains","")).casefold() in json.dumps(x,ensure_ascii=False).casefold()]
            elif action=="json_array_slice":obj=obj[max(0,int(step.get("start",0))):max(0,int(step.get("end",MAX_ITEMS)))]
            elif action=="json_array_flatten":
                flat=[]
                def flat_list(v):
                    for x in v:flat_list(x) if isinstance(x,list) else flat.append(x)
                flat_list(obj);obj=flat
            elif action=="json_array_reverse":obj.reverse()
            else:obj=sorted(obj,key=lambda x:str(x).casefold(),reverse=bool(step.get("descending",False)))
            return {"status":"succeeded","items":obj[:MAX_ITEMS],"count":len(obj)}
        if action=="json_flatten":
            flat={}
            def flat_obj(v,p="$"):
                if isinstance(v,dict):
                    for k,x in v.items():flat_obj(x,p+"."+str(k))
                elif isinstance(v,list):
                    for i,x in enumerate(v):flat_obj(x,p+"["+str(i)+"]")
                else:flat[p]=v
            flat_obj(obj);return {"status":"succeeded","values":dict(list(flat.items())[:MAX_ITEMS]),"count":len(flat)}
        if action=="json_path_values":
            vals=[]
            def paths(v,p="$"):
                vals.append({"path":p,"type":type(v).__name__,"value":v if not isinstance(v,(dict,list)) else None})
                if isinstance(v,dict):
                    for k,x in list(v.items())[:MAX_ITEMS]:paths(x,p+"."+str(k))
                elif isinstance(v,list):
                    for i,x in enumerate(v[:MAX_ITEMS]):paths(x,p+"["+str(i)+"]")
            paths(obj);return {"status":"succeeded","paths":vals[:MAX_ITEMS],"count":len(vals)}
        if action in {"json_count_nodes","json_max_depth","json_extract_strings","json_extract_numbers","json_extract_booleans","json_extract_nulls"}:
            vals=[];depth=0
            def visit(v,d=0):
                nonlocal depth
                vals.append(v);depth=max(depth,d)
                if isinstance(v,dict):
                    for x in v.values():visit(x,d+1)
                elif isinstance(v,list):
                    for x in v:visit(x,d+1)
            visit(obj)
            if action=="json_count_nodes":return {"status":"succeeded","node_count":len(vals)}
            if action=="json_max_depth":return {"status":"succeeded","max_depth":depth}
            typ={"json_extract_strings":str,"json_extract_numbers":(int,float),"json_extract_booleans":bool}.get(action)
            if action=="json_extract_nulls":out=[x for x in vals if x is None]
            elif action=="json_extract_numbers":out=[x for x in vals if isinstance(x,typ) and not isinstance(x,bool)]
            else:out=[x for x in vals if isinstance(x,typ)]
            return {"status":"succeeded","items":out[:MAX_ITEMS],"count":len(out)}
        if action=="sort_json_keys":return {"status":"succeeded","json":json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)[:MAX_TEXT]}
        if action=="json_pretty_print":return {"status":"succeeded","json":json.dumps(obj,ensure_ascii=False,indent=2)[:MAX_TEXT]}
        return {"status":"succeeded","json":json.dumps(obj,ensure_ascii=False,separators=(",",":"))[:MAX_TEXT]}
    if action in {"csv_column_values","csv_column_count","csv_count_blank_cells","csv_column_trim","csv_column_lowercase","csv_column_uppercase","csv_filter_exact","csv_filter_numeric","csv_fill_blank_cells","csv_rename_columns","csv_drop_columns","csv_append_row","csv_prepend_row","csv_column_to_json","csv_sort_by_numeric","csv_to_xml_preview","csv_column_sum","csv_column_average","csv_column_min_max","csv_transpose","csv_group_count","csv_find_duplicates","csv_remove_duplicates","csv_to_sql_inserts_preview","csv_column_median","csv_column_frequency","csv_validate_email_column","csv_validate_numbers"}:
        try:rows=list(csv.DictReader(io.StringIO(value)))[:5000]
        except csv.Error as exc:return {"status":"failed","message":str(exc)}
        headers=list(rows[0].keys()) if rows else next(csv.reader(io.StringIO(value)),[])
        if not headers:return {"status":"failed","message":"CSV must have headers."}
        col=step.get("column")
        if action=="csv_count_blank_cells":return {"status":"succeeded","blank_cells":sum(not str(v or "").strip() for r in rows for v in r.values())}
        if action=="csv_rename_columns":
            mapping=step.get("mapping",{})
            if not isinstance(mapping,dict) or any(k not in headers or not isinstance(v,str) or not v.strip() for k,v in mapping.items()):return {"status":"failed","message":"mapping must map existing headers to new names."}
            headers=[mapping.get(h,h) for h in headers];rows=[{mapping.get(k,k):v for k,v in r.items()} for r in rows]
        elif action=="csv_drop_columns":
            cols=step.get("columns",[]);headers=[h for h in headers if h not in cols];rows=[{k:v for k,v in r.items() if k in headers} for r in rows]
        elif action in {"csv_column_values","csv_column_count","csv_column_trim","csv_column_lowercase","csv_column_uppercase","csv_filter_exact","csv_filter_numeric","csv_fill_blank_cells","csv_column_to_json","csv_sort_by_numeric","csv_column_sum","csv_column_average","csv_column_min_max","csv_column_median","csv_group_count","csv_column_frequency","csv_validate_email_column","csv_validate_numbers"}:
            if col not in headers:return {"status":"failed","message":"Provide an existing column name."}
            vals=[str(r.get(col,"") or "") for r in rows]
            if action=="csv_column_values":return {"status":"succeeded","values":vals[:MAX_ITEMS],"count":len(vals)}
            if action=="csv_column_count":return {"status":"succeeded","count":len(vals),"non_empty":sum(bool(x.strip()) for x in vals)}
            if action=="csv_column_to_json":return {"status":"succeeded","json":json.dumps(vals,ensure_ascii=False)}
            if action=="csv_group_count" or action=="csv_column_frequency":return {"status":"succeeded","frequencies":dict(Counter(vals).most_common(MAX_ITEMS))}
            if action=="csv_validate_email_column":
                good=[x for x in vals if re.fullmatch(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",x,re.I)]
                return {"status":"succeeded","valid_count":len(good),"invalid_values":[x for x in vals if x and x not in good][:MAX_ITEMS]}
            if action=="csv_validate_numbers":
                good=[]
                for x in vals:
                    try:good.append(float(x.replace(",","")))
                    except ValueError:pass
                return {"status":"succeeded","valid_count":len(good),"invalid_values":[x for x in vals if x and not re.fullmatch(r"-?\d+(?:\.\d+)?",x.replace(",",""))][:MAX_ITEMS]}
            if action in {"csv_column_sum","csv_column_average","csv_column_min_max","csv_column_median"}:
                nums=[]
                for x in vals:
                    try:nums.append(float(x.replace(",","")))
                    except ValueError:pass
                if not nums:return {"status":"failed","message":"No numeric values in column."}
                if action=="csv_column_sum":res=sum(nums)
                elif action=="csv_column_average":res=statistics.mean(nums)
                elif action=="csv_column_median":res=statistics.median(nums)
                else:return {"status":"succeeded","min":min(nums),"max":max(nums),"count":len(nums)}
                return {"status":"succeeded","result":res,"count":len(nums)}
            if action=="csv_column_trim":
                for r in rows:r[col]=str(r.get(col,"") or "").strip()
            elif action=="csv_column_lowercase":
                for r in rows:r[col]=str(r.get(col,"") or "").lower()
            elif action=="csv_column_uppercase":
                for r in rows:r[col]=str(r.get(col,"") or "").upper()
            elif action=="csv_sort_by_numeric":
                def num(r):
                    try:return float(str(r.get(col,"")).replace(",",""))
                    except ValueError:return float("-inf")
                rows.sort(key=num,reverse=bool(step.get("descending",False)))
            elif action=="csv_filter_exact":rows=[r for r in rows if str(r.get(col,""))==str(step.get("equals",""))]
            elif action=="csv_filter_numeric":
                try:limit=float(step.get("value",0))
                except (TypeError,ValueError):return {"status":"failed","message":"value must be numeric."}
                op=step.get("operator",">=")
                def match(x):
                    try:n=float(str(x).replace(",",""))
                    except ValueError:return False
                    return {">=":n>=limit,">":n>limit,"<=":n<=limit,"<":n<limit,"==":n==limit}.get(op,False)
                rows=[r for r in rows if match(r.get(col))]
            elif action=="csv_fill_blank_cells":
                fill=str(step.get("fill",""))
                for r in rows:
                    if not str(r.get(col,"") or "").strip():r[col]=fill
        elif action in {"csv_append_row","csv_prepend_row"}:
            row=step.get("row")
            if not isinstance(row,dict):return {"status":"failed","message":"row must be an object."}
            record={h:str(row.get(h,"")) for h in headers}
            rows=([record]+rows) if action=="csv_prepend_row" else rows+[record]
        elif action in {"csv_find_duplicates","csv_remove_duplicates"}:
            seen=set();dups=[];unique=[]
            for r in rows:
                k=json.dumps(r,sort_keys=True)
                if k in seen:dups.append(r)
                else:seen.add(k);unique.append(r)
            if action=="csv_find_duplicates":return {"status":"succeeded","duplicates":dups[:MAX_ITEMS],"count":len(dups)}
            rows=unique
        elif action=="csv_transpose":
            matrix=[headers]+[[r.get(h,"") for h in headers] for r in rows];out=io.StringIO();csv.writer(out).writerows(list(map(list,zip(*matrix))))
            return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT]}
        elif action=="csv_to_sql_inserts_preview":
            table=step.get("table","records")
            if not isinstance(table,str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",table):return {"status":"failed","message":"table must be a SQL identifier."}
            statements=["INSERT INTO "+table+" ("+", ".join(headers)+") VALUES ("+", ".join("NULL" if not r.get(h) else "'"+str(r.get(h)).replace("'","''")+"'" for h in headers)+");" for r in rows[:100]]
            return {"status":"succeeded","sql_preview":"\n".join(statements)[:MAX_TEXT],"note":"Preview only; SQL is never executed."}
        elif action=="csv_to_xml_preview":
            esc=lambda x:html.escape(str(x or ""))
            xml="<rows>"+"".join("<row>"+"".join("<"+re.sub(r"[^A-Za-z0-9_-]","_",h)+">"+esc(r.get(h,""))+"</"+re.sub(r"[^A-Za-z0-9_-]","_",h)+">" for h in headers)+"</row>" for r in rows[:200])+"</rows>"
            return {"status":"succeeded","xml_preview":xml[:MAX_TEXT],"rows":len(rows)}
        out=io.StringIO();writer=csv.DictWriter(out,fieldnames=headers);writer.writeheader();writer.writerows(rows)
        return {"status":"succeeded","csv":out.getvalue()[:MAX_TEXT],"row_count":len(rows)}
    if action in {"count_non_ascii","extract_ascii","remove_non_ascii","replace_regex","split_by_regex","join_unique_lines","count_unique_lines","extract_line_numbers","line_length_stats","word_length_stats","extract_capitalized_words","extract_quoted_strings","extract_parenthetical_text","extract_bracket_contents","normalize_quotes","normalize_dashes","normalize_bullets","remove_duplicate_spaces","remove_trailing_spaces","remove_leading_spaces","strip_markdown_links"}:
        if action=="count_non_ascii":return {"status":"succeeded","count":sum(ord(x)>127 for x in value)}
        if action in {"extract_ascii","remove_non_ascii"}:return {"status":"succeeded","text":"".join(x for x in value if ord(x)<128)}
        if action=="replace_regex":
            pat=step.get("pattern","")
            if not isinstance(pat,str) or not pat or len(pat)>300:return {"status":"failed","message":"Provide regex pattern up to 300 characters."}
            try:res=re.sub(pat,str(step.get("replacement","")),value,count=max(0,min(10000,int(step.get("count",0))))
            except re.error as exc:return {"status":"failed","message":"Invalid regex: "+str(exc)}
            return {"status":"succeeded","text":res[:MAX_TEXT]}
        if action=="split_by_regex":
            pat=step.get("pattern",r"\s+")
            try:res=re.split(pat,value)
            except re.error as exc:return {"status":"failed","message":"Invalid regex: "+str(exc)}
            return {"status":"succeeded","items":res[:MAX_ITEMS],"count":len(res)}
        if action in {"join_unique_lines","count_unique_lines"}:
            unique=list(dict.fromkeys(lines))
            return {"status":"succeeded","unique_line_count":len(unique),"text":str(step.get("separator","\n")).join(unique)[:MAX_TEXT],"total_lines":len(lines)}
        if action=="extract_line_numbers":
            pat=step.get("pattern",".")
            try:vals=[{"line":i,"text":x} for i,x in enumerate(lines,1) if re.search(pat,x)]
            except re.error as exc:return {"status":"failed","message":"Invalid regex: "+str(exc)}
            return {"status":"succeeded","lines":vals[:MAX_ITEMS],"count":len(vals)}
        if action=="line_length_stats":
            vals=[len(x) for x in lines];return {"status":"succeeded","count":len(vals),"min":min(vals) if vals else 0,"max":max(vals) if vals else 0,"average":sum(vals)/len(vals) if vals else 0}
        if action=="word_length_stats":
            vals=[len(x) for x in re.findall(r"\b[\w'-]+\b",value)];return {"status":"succeeded","count":len(vals),"min":min(vals) if vals else 0,"max":max(vals) if vals else 0,"average":sum(vals)/len(vals) if vals else 0}
        if action=="extract_capitalized_words":vals=re.findall(r"\b[A-Z][a-z]+\b",value)
        elif action=="extract_quoted_strings":vals=re.findall(r"""["'](.*?)["']""",value)
        elif action=="extract_parenthetical_text":vals=re.findall(r"\(([^()]*)\)",value)
        elif action=="extract_bracket_contents":
            vals=re.findall(r"\[([^\[\]]*)\]|\{([^{}]*)\}|\(([^()]*)\)",value);vals=[next((z for z in x if z),"") for x in vals]
        elif action=="normalize_quotes":return {"status":"succeeded","text":value.translate(str.maketrans({"“":'"',"”":'"',"‘":"'","’":"'"}))}
        elif action=="normalize_dashes":return {"status":"succeeded","text":value.translate(str.maketrans({"–":"-","—":"-","−":"-"}))}
        elif action=="normalize_bullets":return {"status":"succeeded","text":re.sub(r"(?m)^\s*[•●▪]\s*","- ",value)}
        elif action=="remove_duplicate_spaces":return {"status":"succeeded","text":re.sub(r"[ \t]{2,}"," ",value)}
        elif action=="remove_trailing_spaces":return {"status":"succeeded","text":re.sub(r"(?m)[ \t]+$","",value)}
        elif action=="remove_leading_spaces":return {"status":"succeeded","text":re.sub(r"(?m)^[ \t]+","",value)}
        else:return {"status":"succeeded","text":re.sub(r"\[([^\]]+)\]\([^)]+\)",r"\1",value)}
        return {"status":"succeeded","items":list(dict.fromkeys(vals))[:MAX_ITEMS]}
    if action in {"validate_url","validate_domain","validate_phone_candidate","validate_date_iso","validate_datetime_iso","validate_json_lines","validate_csv","validate_xml_wellformed","validate_semver","validate_hex_color","validate_mac","validate_ipv6","validate_port","validate_base64","validate_sha256","validate_slug","validate_credit_card_candidate"}:
        if action=="validate_url":
            p=urlparse(value.strip());return {"status":"succeeded","valid":p.scheme in {"http","https"} and bool(p.hostname)}
        if action=="validate_domain":return {"status":"succeeded","valid":bool(re.fullmatch(r"(?i)(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",value.strip()))}
        if action=="validate_phone_candidate":return {"status":"succeeded","valid":bool(re.fullmatch(r"\+?[\d ()-]{7,25}",value.strip())) and sum(x.isdigit() for x in value)>=7}
        if action=="validate_date_iso":
            try:datetime.strptime(value.strip(),"%Y-%m-%d");ok=True
            except ValueError:ok=False
            return {"status":"succeeded","valid":ok}
        if action=="validate_datetime_iso":
            try:datetime.fromisoformat(value.strip().replace("Z","+00:00"));ok=True
            except ValueError:ok=False
            return {"status":"succeeded","valid":ok}
        if action=="validate_json_lines":
            bad=[]
            for i,line in enumerate(lines,1):
                if line.strip():
                    try:json.loads(line)
                    except json.JSONDecodeError:bad.append(i)
            return {"status":"succeeded","valid":not bad,"invalid_line_numbers":bad[:MAX_ITEMS]}
        if action=="validate_csv":
            try:rows=list(csv.reader(io.StringIO(value)));widths=[len(r) for r in rows];ok=bool(rows) and len(set(widths))==1
            except csv.Error:rows=[];widths=[];ok=False
            return {"status":"succeeded","valid":ok,"rows":len(rows),"column_counts":list(dict.fromkeys(widths))}
        if action=="validate_xml_wellformed":
            import xml.etree.ElementTree as ET
            try:ET.fromstring(value);return {"status":"succeeded","valid":True}
            except ET.ParseError as exc:return {"status":"succeeded","valid":False,"error":str(exc)}
        patterns={"validate_semver":r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?","validate_hex_color":r"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})","validate_mac":r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}","validate_sha256":r"(?i)[0-9a-f]{64}","validate_slug":r"[a-z0-9]+(?:-[a-z0-9]+)*","validate_port":r"\d{1,5}","validate_credit_card_candidate":r"(?:\d[ -]?){13,19}"}
        if action=="validate_ipv6":
            import ipaddress
            try:ipaddress.IPv6Address(value.strip());ok=True
            except ValueError:ok=False
        elif action=="validate_base64":
            import base64
            try:base64.b64decode(value,validate=True);ok=True
            except Exception:ok=False
        else:
            ok=bool(re.fullmatch(patterns.get(action,"(?!)"),value.strip()))
            if action=="validate_port":ok=ok and 1<=int(value.strip())<=65535
            if action=="validate_credit_card_candidate":
                digits=re.sub(r"\D","",value);total=0;parity=len(digits)%2
                for i,ch in enumerate(digits):
                    n=int(ch)
                    if i%2==parity:n*=2;n=n-9 if n>9 else n
                    total+=n
                ok=ok and 13<=len(digits)<=19 and total%10==0
        return {"status":"succeeded","valid":ok}
    if action in {"calculate_mean","calculate_mode","calculate_variance","calculate_standard_deviation","calculate_range","calculate_ratio","calculate_proportion","calculate_markup","calculate_profit_margin","calculate_compound_growth","calculate_tip","calculate_split_bill","calculate_gcd","calculate_lcm","is_prime","factorize_integer","convert_number_base","binary_to_decimal","decimal_to_binary","roman_to_integer","integer_to_roman"}:
        nums=[float(x) for x in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?",value)]
        if action in {"calculate_gcd","calculate_lcm","is_prime","factorize_integer","convert_number_base","binary_to_decimal","decimal_to_binary","roman_to_integer","integer_to_roman"}:
            try:n=int(step.get("number",nums[0] if nums else value.strip()))
            except (ValueError,TypeError):return {"status":"failed","message":"Provide an integer."}
            if action=="is_prime":return {"status":"succeeded","is_prime":n>=2 and all(n%d for d in range(2,int(n**0.5)+1))}
            if action=="factorize_integer":
                if n==0:return {"status":"failed","message":"Zero has no finite prime factorization."}
                x=abs(n);factors=[];d=2
                while d*d<=x and len(factors)<10000:
                    while x%d==0:factors.append(d);x//=d
                    d+=1
                if x>1:factors.append(x)
                return {"status":"succeeded","factors":factors,"negative":n<0}
            if action in {"binary_to_decimal","decimal_to_binary","convert_number_base"}:
                try:
                    if action=="binary_to_decimal":res=int(value.strip(),2)
                    elif action=="decimal_to_binary":res=bin(n)[2:]
                    else:
                        base=int(step.get("base",10))
                        if not 2<=base<=36:return {"status":"failed","message":"base must be 2–36."}
                        alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";x=abs(n);res="0" if x==0 else ""
                        while x:res=alphabet[x%base]+res;x//=base
                        if n<0:res="-"+res
                except ValueError:return {"status":"failed","message":"Invalid base conversion input."}
                return {"status":"succeeded","result":res}
            if action=="calculate_gcd":
                import math
                b=int(step.get("second_number",nums[1] if len(nums)>1 else 0));return {"status":"succeeded","result":math.gcd(n,b)}
            if action=="calculate_lcm":
                import math
                b=int(step.get("second_number",nums[1] if len(nums)>1 else 0));return {"status":"succeeded","result":abs(n*b)//math.gcd(n,b) if n and b else 0}
            if action=="integer_to_roman":
                if not 1<=n<=3999:return {"status":"failed","message":"Roman range is 1–3999."}
                out=""
                for v,s in [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]:
                    while n>=v:out+=s;n-=v
                return {"status":"succeeded","roman":out}
            vals={"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000};total=0;s=value.strip().upper()
            for i,ch in enumerate(s):
                if ch not in vals:return {"status":"failed","message":"Invalid Roman numeral."}
                total+=-vals[ch] if i+1<len(s) and vals[ch]<vals.get(s[i+1],0) else vals[ch]
            return {"status":"succeeded","integer":total}
        if action in {"calculate_ratio","calculate_proportion","calculate_markup","calculate_profit_margin","calculate_compound_growth","calculate_tip","calculate_split_bill"}:
            a=float(step.get("amount",nums[0] if nums else 0));b=float(step.get("second_amount",nums[1] if len(nums)>1 else 1));rate=float(step.get("rate",nums[1] if len(nums)>1 else 0))/100
            if action=="calculate_ratio":res=None if b==0 else a/b
            elif action=="calculate_proportion":res=None if b==0 else a/b*100
            elif action=="calculate_markup":res=a*(1+rate)
            elif action=="calculate_profit_margin":res=None if a==0 else (a-b)/a*100
            elif action=="calculate_compound_growth":res=None if a==0 else ((b/a)**(1/max(1,float(step.get("periods",1))))-1)*100
            elif action=="calculate_tip":res=a*rate
            else:res=a/max(1,int(step.get("people",2)))
            return {"status":"succeeded","result":res}
        if not nums:return {"status":"failed","message":"Provide numeric values."}
        if action=="calculate_mean":res=statistics.mean(nums)
        elif action=="calculate_mode":return {"status":"succeeded","modes":statistics.multimode(nums)}
        elif action=="calculate_variance":res=statistics.pvariance(nums)
        elif action=="calculate_standard_deviation":res=statistics.pstdev(nums)
        else:res=max(nums)-min(nums)
        return {"status":"succeeded","result":res,"count":len(nums)}
    if action in {"unix_to_datetime","datetime_to_unix","seconds_to_duration","duration_to_seconds","days_until_date","weekday_for_date","count_weekdays","next_weekday","add_months","iso_week_number","quarter_for_date"}:
        if action=="unix_to_datetime":
            try:dt=datetime.fromtimestamp(float(value.strip()),timezone.utc)
            except (ValueError,OverflowError,OSError):return {"status":"failed","message":"Invalid Unix timestamp."}
            return {"status":"succeeded","datetime":dt.isoformat()}
        if action=="datetime_to_unix":
            try:dt=datetime.fromisoformat(value.strip().replace("Z","+00:00"))
            except ValueError:return {"status":"failed","message":"Provide ISO datetime."}
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            return {"status":"succeeded","timestamp":dt.timestamp()}
        if action=="seconds_to_duration":
            try:n=max(0,int(value.strip()))
            except ValueError:return {"status":"failed","message":"Provide seconds as an integer."}
            d,r=divmod(n,86400);h,r=divmod(r,3600);m,s=divmod(r,60)
            return {"status":"succeeded","days":d,"hours":h,"minutes":m,"seconds":s,"formatted":f"{d}d {h}h {m}m {s}s"}
        if action=="duration_to_seconds":
            total=sum(int(n)*{"d":86400,"h":3600,"m":60,"s":1}[u] for n,u in re.findall(r"(\d+)\s*(d|h|m|s)",value.lower()))
            return {"status":"succeeded","seconds":total}
        try:dt=datetime.fromisoformat(str(step.get("date",value)).replace("Z","+00:00"))
        except ValueError:return {"status":"failed","message":"Provide ISO date."}
        if action=="days_until_date":return {"status":"succeeded","days":(dt.date()-datetime.now(timezone.utc).date()).days}
        if action=="weekday_for_date":return {"status":"succeeded","weekday":dt.strftime("%A"),"weekday_number_monday_zero":dt.weekday()}
        if action=="iso_week_number":return {"status":"succeeded","iso_year":dt.isocalendar().year,"week":dt.isocalendar().week}
        if action=="quarter_for_date":return {"status":"succeeded","quarter":(dt.month-1)//3+1}
        if action=="next_weekday":
            target=int(step.get("weekday",0))
            if not 0<=target<=6:return {"status":"failed","message":"weekday must be 0–6."}
            delta=(target-dt.weekday())%7 or 7;return {"status":"succeeded","date":(dt+timedelta(days=delta)).date().isoformat()}
        if action=="count_weekdays":
            try:end=datetime.fromisoformat(str(step.get("end_date","")).replace("Z","+00:00")).date()
            except ValueError:return {"status":"failed","message":"Provide end_date."}
            start=dt.date();lo,hi=sorted((start,end));n=sum((lo+timedelta(days=i)).weekday()<5 for i in range((hi-lo).days+1))
            return {"status":"succeeded","weekdays":n if end>=start else -n}
        if action=="add_months":
            import calendar
            idx=dt.year*12+dt.month-1+int(step.get("months",0));year,month0=divmod(idx,12);month=month0+1;day=min(dt.day,calendar.monthrange(year,month)[1])
            return {"status":"succeeded","date":dt.replace(year=year,month=month,day=day).isoformat()}
    return None
