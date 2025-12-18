import os
import pytest
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.link_processor import (
    LinkProcessor, LinkType, LinkContext,
    ImageHandler, MermaidHandler, TocHandler, AnchorHandler
)

pytestmark = pytest.mark.skipif(os.environ.get("LAD_RUN_013_TESTS") != "1", reason="013 tests gated")

def test_image_route():
    logger = logging.getLogger("lp-misc-img")
    logger.setLevel(logging.INFO)
    p = LinkProcessor(logger=logger)
    p.set_handlers({LinkType.IMAGE: ImageHandler()})
    res = p.process_link(LinkContext(href="images/pic.png"))
    assert res.success is True
    assert res.action == "open_image_viewer"

def test_mermaid_route():
    logger = logging.getLogger("lp-misc-mermaid")
    logger.setLevel(logging.INFO)
    p = LinkProcessor(logger=logger)
    p.set_handlers({LinkType.MERMAID: MermaidHandler()})
    res = p.process_link(LinkContext(href="graph.mmd", extra={"mermaid_container": True}))
    assert res.success is True
    assert res.action == "open_mermaid_viewer"

def test_toc_route():
    logger = logging.getLogger("lp-misc-toc")
    logger.setLevel(logging.INFO)
    p = LinkProcessor(logger=logger)
    p.set_handlers({LinkType.TOC: TocHandler()})
    res = p.process_link(LinkContext(href="docs/guide.md#intro"))
    assert res.success is True
    assert res.action == "scroll_to_anchor"

def test_anchor_route():
    logger = logging.getLogger("lp-misc-anchor")
    logger.setLevel(logging.INFO)
    p = LinkProcessor(logger=logger)
    p.set_handlers({LinkType.ANCHOR: AnchorHandler()})
    res = p.process_link(LinkContext(href="#section-1"))
    assert res.success is True
    assert res.action == "scroll_to_anchor"
