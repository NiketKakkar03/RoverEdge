import asyncio
import base64
import hashlib
import os
import time
from collections.abc import AsyncIterable
from dataclasses import replace
from json import loads
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from meta_sam_parser import (
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)
from openai import AsyncOpenAI

from .models import GroundingEvidence, GroundingMask, GroundingMatch
from .scene_rendering import RenderedScene


class GroundingAdapter(Protocol):
    def ground(self, render: RenderedScene, phrase: str) -> GroundingEvidence: ...


class MetaSamGroundingAdapter:
    def __init__(self) -> None:
        self.last_raw_output: str | None = None

    def ground(self, render: RenderedScene, phrase: str) -> GroundingEvidence:
        api_key = os.environ.get("MODEL_API_KEY")
        if not api_key:
            return _unavailable(render, phrase, "MODEL_API_KEY is not set in the process")
        return asyncio.run(self._ground_async(render, phrase, api_key))

    async def _ground_async(
        self, render: RenderedScene, phrase: str, api_key: str
    ) -> GroundingEvidence:
        started = time.monotonic()
        client = AsyncOpenAI(base_url="https://api.meta.ai/v1", api_key=api_key)
        try:
            encoded = base64.b64encode(render.png_bytes).decode("ascii")
            stream = await client.responses.create(
                model="sam-3.1",
                input=cast(
                    Any,
                    [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": phrase},
                                {
                                    "type": "input_image",
                                    "image_url": f"data:image/png;base64,{encoded}",
                                },
                            ],
                        }
                    ],
                ),
                stream=True,
                metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
            )
            result = await parse_responses_stream(
                cast(AsyncIterable[Any], stream), image_segmentation_format()
            ).final_result()
            self.last_raw_output = result.raw_output
            if result.outcome.status != "completed":
                return _unavailable(
                    render,
                    phrase,
                    f"provider stream ended {result.outcome.status}",
                    duration_s=time.monotonic() - started,
                    raw_output=result.raw_output,
                )
            boxes = {
                record.object_id: record
                for record in result.records
                if isinstance(record, SegmentationBoxRecord)
            }
            matches: list[GroundingMatch] = []
            for ordinal, mask_record in enumerate(
                record for record in result.records if isinstance(record, SegmentationMaskRecord)
            ):
                raster = decode_mask_to_raster(mask_record.mask)
                box = boxes.get(mask_record.object_id)
                if box is None:
                    raise ValueError("provider returned a mask without a matching box")
                bounds = mask_record.bounds
                left_px = round(bounds.left)
                top_px = round(bounds.top)
                right_px = round(bounds.right)
                bottom_px = round(bounds.bottom)
                if (left_px, top_px, right_px, bottom_px) != (
                    round(box.left),
                    round(box.top),
                    round(box.right),
                    round(box.bottom),
                ):
                    raise ValueError("provider mask bounds do not match its box")
                matches.append(
                    GroundingMatch(
                        ordinal=ordinal,
                        box_px=(
                            round(box.left),
                            round(box.top),
                            round(box.right),
                            round(box.bottom),
                        ),
                        mask=GroundingMask(
                            width_px=render.width_px,
                            height_px=render.height_px,
                            counts=_box_local_raster_to_counts(
                                raster,
                                mask_width_px=mask_record.mask.width,
                                mask_height_px=mask_record.mask.height,
                                render_width_px=render.width_px,
                                render_height_px=render.height_px,
                                left_px=left_px,
                                top_px=top_px,
                            ),
                        ),
                        confidence=mask_record.confidence,
                    )
                )
            status: Literal["matched", "target_not_found", "target_ambiguous"] = (
                "matched"
                if len(matches) == 1
                else "target_not_found"
                if not matches
                else "target_ambiguous"
            )
            return GroundingEvidence(
                source="live",
                status=status,
                provider="meta-model-api",
                model="sam-3.1",
                parser_version="meta-sam-parser-0.1.0",
                target_phrase=phrase,
                render_sha256=render.sha256,
                render_width_px=render.width_px,
                render_height_px=render.height_px,
                duration_s=time.monotonic() - started,
                raw_output_sha256=hashlib.sha256(result.raw_output.encode()).hexdigest(),
                matches=tuple(matches),
                selected_match_ordinal=0 if len(matches) == 1 else None,
                diagnostics=tuple(
                    f"{diagnostic.severity}:{diagnostic.code}:{diagnostic.message}"
                    for diagnostic in result.diagnostics
                ),
            )
        except Exception as error:
            return _unavailable(
                render,
                phrase,
                f"{type(error).__name__}: {error}",
                duration_s=time.monotonic() - started,
            )
        finally:
            await client.close()


class RecordedGroundingAdapter:
    def __init__(self, evidence: GroundingEvidence) -> None:
        self._evidence = replace(evidence, source="recorded")

    @classmethod
    def from_file(cls, path: Path) -> "RecordedGroundingAdapter":
        if not path.is_file():
            raise ValueError("recorded grounding evidence is unavailable for this request")
        document = loads(path.read_text())
        if "evidence" in document:
            document = document["evidence"]
        matches = tuple(
            GroundingMatch(
                ordinal=match["ordinal"],
                box_px=tuple(match["box_px"]),
                mask=GroundingMask(
                    width_px=match["mask"]["width_px"],
                    height_px=match["mask"]["height_px"],
                    counts=tuple(match["mask"]["counts"]),
                    encoding=match["mask"].get("encoding", "row_major_rle_v1"),
                ),
                confidence=match.get("confidence"),
            )
            for match in document["matches"]
        )
        return cls(
            GroundingEvidence(
                source=document["source"],
                status=document["status"],
                provider=document["provider"],
                model=document["model"],
                parser_version=document["parser_version"],
                target_phrase=document["target_phrase"],
                render_sha256=document["render_sha256"],
                render_width_px=document["render_width_px"],
                render_height_px=document["render_height_px"],
                duration_s=document["duration_s"],
                raw_output_sha256=document["raw_output_sha256"],
                matches=matches,
                selected_match_ordinal=document.get("selected_match_ordinal"),
                diagnostics=tuple(document.get("diagnostics", ())),
                request_id=document.get("request_id"),
            )
        )

    def ground(self, render: RenderedScene, phrase: str) -> GroundingEvidence:
        return self._evidence


def validate_grounding_evidence(
    evidence: GroundingEvidence, render: RenderedScene, phrase: str
) -> None:
    if evidence.target_phrase != phrase:
        raise ValueError("grounding evidence target phrase does not match the request")
    if evidence.render_sha256 != render.sha256:
        raise ValueError("grounding evidence render hash does not match the scenario render")
    if (evidence.render_width_px, evidence.render_height_px) != (
        render.width_px,
        render.height_px,
    ):
        raise ValueError("grounding evidence dimensions do not match the scenario render")
    expected_status = (
        "matched"
        if len(evidence.matches) == 1
        else "target_not_found"
        if not evidence.matches
        else "target_ambiguous"
    )
    if evidence.status != "provider_unavailable" and evidence.status != expected_status:
        raise ValueError("grounding status does not match the number of returned masks")
    for match in evidence.matches:
        if (match.mask.width_px, match.mask.height_px) != (
            render.width_px,
            render.height_px,
        ):
            raise ValueError("grounding mask dimensions do not match the scenario render")
        if sum(match.mask.counts) != render.width_px * render.height_px:
            raise ValueError("grounding mask RLE length does not match the scenario render")


def _raster_to_counts(raster: bytes) -> tuple[int, ...]:
    counts: list[int] = []
    current = 0
    run = 0
    for value in raster:
        if value not in (0, 1):
            raise ValueError("decoded grounding mask must contain only binary pixels")
        if value == current:
            run += 1
        else:
            counts.append(run)
            current = value
            run = 1
    counts.append(run)
    return tuple(counts)


def _box_local_raster_to_counts(
    raster: bytes,
    *,
    mask_width_px: int,
    mask_height_px: int,
    render_width_px: int,
    render_height_px: int,
    left_px: int,
    top_px: int,
) -> tuple[int, ...]:
    if len(raster) != mask_width_px * mask_height_px:
        raise ValueError("decoded grounding mask dimensions do not match its raster")
    if (
        left_px < 0
        or top_px < 0
        or left_px + mask_width_px > render_width_px
        or top_px + mask_height_px > render_height_px
    ):
        raise ValueError("grounding mask bounds are outside the scenario render")
    full_raster = bytearray(render_width_px * render_height_px)
    for row in range(mask_height_px):
        source_start = row * mask_width_px
        destination_start = (top_px + row) * render_width_px + left_px
        full_raster[destination_start : destination_start + mask_width_px] = raster[
            source_start : source_start + mask_width_px
        ]
    return _raster_to_counts(bytes(full_raster))


def _unavailable(
    render: RenderedScene,
    phrase: str,
    diagnostic: str,
    *,
    duration_s: float = 0.0,
    raw_output: str = "",
) -> GroundingEvidence:
    return GroundingEvidence(
        source="live",
        status="provider_unavailable",
        provider="meta-model-api",
        model="sam-3.1",
        parser_version="meta-sam-parser-0.1.0",
        target_phrase=phrase,
        render_sha256=render.sha256,
        render_width_px=render.width_px,
        render_height_px=render.height_px,
        duration_s=duration_s,
        raw_output_sha256=hashlib.sha256(raw_output.encode()).hexdigest(),
        matches=(),
        diagnostics=(diagnostic,),
    )
