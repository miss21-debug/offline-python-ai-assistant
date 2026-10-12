"""Reject incomplete or malformed model responses before they become source."""
import json
import urllib.error
import urllib.request


def request_chat(url, payload, opener, timeout=600):
    messages = payload.get('messages', [])
    context = payload.get('options', {}).get('num_ctx', 8192)
    # Conservative estimate only; never truncate the question silently.
    content = '\n'.join(message.get('content', '') for message in messages)
    estimated = sum(1 if ord(ch) > 127 else 1 / 3 for ch in content) + len(messages) * 10
    if estimated > context - 1536:
        raise ValueError('单次题目及代码预估超出模型上下文，请拆分题目或缩短参考代码；本次没有截取或丢弃内容')
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
    try:
        with opener(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(f'找不到模型 {payload.get("model")} 或请求地址，请先安装模型并核对配置') from exc
        raise RuntimeError(f'模型服务返回 HTTP {exc.code}，本次未获得完整结果') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError('模型连接中断或等待超时，请检查本地 Ollama 服务后重试') from exc
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError('模型响应不是完整的 JSON，未保存本次结果') from exc
    if not isinstance(data, dict):
        raise RuntimeError('模型响应格式错误')
    if data.get('error'):
        raise RuntimeError(f'模型服务错误：{data["error"]}')
    if data.get('done') is False or data.get('done_reason') in ('length', 'max_tokens'):
        raise RuntimeError('模型输出达到长度限制或尚未完成，已拒绝保存残缺代码；请拆分题目后重试')
    message = data.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError('模型没有返回最终回答，已拒绝保存空文件')
    return content
