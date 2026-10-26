"""Bounded deterministic handlers for additional text/data actions."""
import csv, difflib, html, io, json, re, statistics, textwrap, unicodedata, uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote

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
    return None
