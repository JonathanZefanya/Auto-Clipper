import pytest

from app.pipeline.download import parse_youtube_url

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={VID}",
    f"https://youtube.com/watch?v={VID}&t=120s",
    f"https://m.youtube.com/watch?feature=share&v={VID}",
    f"https://youtu.be/{VID}",
    f"https://youtu.be/{VID}?si=abc",
    f"https://www.youtube.com/live/{VID}",
    f"https://www.youtube.com/live/{VID}?feature=share",
])
def test_valid_urls(url):
    assert parse_youtube_url(url) == VID


@pytest.mark.parametrize("url", [
    "",
    "bukan link",
    "https://vimeo.com/123456",
    "https://www.youtube.com/watch?v=short",
    "https://www.youtube.com/@channel",
    f"https://evil.com/watch?v={VID}",
])
def test_invalid_urls(url):
    with pytest.raises(ValueError, match="Link tidak valid"):
        parse_youtube_url(url)
