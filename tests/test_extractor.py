"""Tests for HTML Extractor and Markdown Cleaner."""

from competitor_radar.extractor import extract_markdown


def test_extract_markdown_basic_content():
    html = """
    <!DOCTYPE html>
    <html>
      <head><title>Acme Pricing</title></head>
      <body>
        <header><nav><a href="/home">Home</a><a href="/about">About</a></nav></header>
        <div id="cookie-consent-banner" class="cookie-banner">Accept all cookies</div>
        <main>
          <h1>Simple, transparent pricing</h1>
          <p>Choose the plan that fits your team.</p>
          <h2>Starter Plan</h2>
          <p>$29 / month per user</p>
          <ul>
            <li>Up to 5 seats</li>
            <li>Basic analytics</li>
          </ul>
        </main>
        <footer><p>&copy; 2026 Acme Corp</p></footer>
        <script>console.log("analytics");</script>
        <style>.cookie-banner { display: block; }</style>
      </body>
    </html>
    """

    res = extract_markdown(html, base_url="https://acme.com")

    assert res.title == "Acme Pricing"
    assert "Simple, transparent pricing" in res.markdown
    assert "Starter Plan" in res.markdown
    assert "$29 / month per user" in res.markdown
    assert "- Up to 5 seats" in res.markdown

    # Assert stripped elements
    assert "Accept all cookies" not in res.markdown
    assert "Home" not in res.markdown
    assert "console.log" not in res.markdown
    assert "display: block" not in res.markdown
    assert "&copy;" not in res.markdown
    assert res.word_count > 0
    assert len(res.content_hash) == 64


def test_extract_tables():
    html = """
    <table>
      <thead>
        <tr><th>Plan</th><th>Price</th><th>Seats</th></tr>
      </thead>
      <tbody>
        <tr><td>Starter</td><td>$19/mo</td><td>3 seats</td></tr>
        <tr><td>Pro</td><td>$49/mo</td><td>10 seats</td></tr>
      </tbody>
    </table>
    """

    res = extract_markdown(html)
    assert res.tables_count == 1
    assert "| Plan | Price | Seats |" in res.markdown
    assert "| --- | --- | --- |" in res.markdown
    assert "| Starter | $19/mo | 3 seats |" in res.markdown
    assert "| Pro | $49/mo | 10 seats |" in res.markdown


def test_empty_html():
    res = extract_markdown("")
    assert res.markdown == ""
    assert res.word_count == 0
    assert res.title == ""
