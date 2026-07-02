const Anthropic = require('@anthropic-ai/sdk');

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed. Use POST.' });
  }

  const { product_description } = req.body || {};
  if (!product_description || typeof product_description !== 'string') {
    return res.status(400).json({ error: 'Missing required field: product_description (string)' });
  }

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

  const prompt =
    `You are a medical device procurement expert. Map this product description to EU CPV codes and search keywords. ` +
    `Product description: ${product_description}. ` +
    `Respond with ONLY valid JSON: { cpv_codes: [], keywords: [], category_summary: '' }. ` +
    `Include 3-8 CPV codes starting with 33 and 5-12 specific keywords.`;

  try {
    const response = await client.messages.create({
      model: 'claude-sonnet-4-5',
      max_tokens: 1024,
      messages: [{ role: 'user', content: prompt }],
    });

    const text = response.content
      .filter((block) => block.type === 'text')
      .map((block) => block.text)
      .join('');

    // Strip markdown code fences if the model wrapped the JSON in them
    const cleaned = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
    const parsed = JSON.parse(cleaned);

    return res.status(200).json({
      cpv_codes: parsed.cpv_codes || [],
      keywords: parsed.keywords || [],
      category_summary: parsed.category_summary || '',
    });
  } catch (err) {
    if (err instanceof Anthropic.APIError) {
      return res.status(502).json({ error: `Anthropic API error (${err.status}): ${err.message}` });
    }
    if (err instanceof SyntaxError) {
      return res.status(502).json({ error: 'Model did not return valid JSON' });
    }
    return res.status(500).json({ error: err.message || 'Internal server error' });
  }
};
