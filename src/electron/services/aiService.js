'use strict';

/**
 * chatCompletion — single-turn, awaitable
 * @param {Array<{role: string, content: string}>} messages
 * @param {{ endpoint: string, apiKey: string, model: string, temperature?: number, maxTokens?: number }} config
 * @returns {Promise<string>} assistant message content
 */
async function chatCompletion(messages, config) {
  const url = config.endpoint.replace(/\/$/, '') + '/chat/completions';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify({
      model: config.model,
      messages,
      temperature: config.temperature ?? 0.7,
      max_tokens: config.maxTokens ?? 2048,
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`AI API error ${response.status}: ${text}`);
  }
  const data = await response.json();
  return data.choices?.[0]?.message?.content ?? '';
}

/**
 * streamCompletion — streams tokens via onChunk callback
 * @param {Array<{role: string, content: string}>} messages
 * @param {{ endpoint: string, apiKey: string, model: string, temperature?: number, maxTokens?: number }} config
 * @param {(text: string) => void} onChunk
 * @param {AbortSignal} [signal]
 */
async function streamCompletion(messages, config, onChunk, signal) {
  const url = config.endpoint.replace(/\/$/, '') + '/chat/completions';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify({
      model: config.model,
      messages,
      temperature: config.temperature ?? 0.7,
      max_tokens: config.maxTokens ?? 2048,
      stream: true,
    }),
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`AI API error ${response.status}: ${text}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed === 'data: [DONE]') continue;
      if (trimmed.startsWith('data: ')) {
        try {
          const json = JSON.parse(trimmed.slice(6));
          const delta = json.choices?.[0]?.delta?.content;
          if (delta) onChunk(delta);
        } catch {
          // skip malformed chunk
        }
      }
    }
  }
}

/**
 * generateImage — OpenAI-compatible images/generations endpoint
 * @param {string} prompt
 * @param {{ endpoint: string, apiKey: string, model?: string, size?: string }} config
 * @returns {Promise<string>} image URL or base64 data URL
 */
async function generateImage(prompt, config) {
  const url = config.endpoint.replace(/\/$/, '') + '/images/generations';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify({
      model: config.model ?? 'dall-e-3',
      prompt,
      n: 1,
      size: config.size ?? '1024x1024',
      response_format: 'url',
    }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Image API error ${response.status}: ${text}`);
  }
  const data = await response.json();
  return data.data?.[0]?.url ?? data.data?.[0]?.b64_json ?? '';
}

export { chatCompletion, streamCompletion, generateImage };
