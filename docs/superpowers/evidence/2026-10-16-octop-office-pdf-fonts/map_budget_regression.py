
def test_combined_character_maps_have_one_total_budget_before_native_parse(monkeypatch):
    data = bytearray(FONT)
    count = struct.unpack_from(">H", data, 4)[0]
    cmap_record = next(12 + i * 16 for i in range(count) if data[12 + i * 16:16 + i * 16] == b"cmap")
    groups = 60_000
    payload = struct.pack(">HHIII", 12, 0, 16 + 12 * groups, 0, groups) + b"".join(struct.pack(">III", 2 * i, 2 * i, 1) for i in range(groups))
    start = 20
    cmap = struct.pack(">HH", 0, 2) + struct.pack(">HHI", 3, 10, start) + struct.pack(">HHI", 0, 4, start + len(payload)) + payload + payload
    struct.pack_into(">II", data, cmap_record + 8, len(data), len(cmap))
    data.extend(cmap)

    def native(*args):
        pytest.fail("Character map budget exceeded before native parsing")

    monkeypatch.setattr(MODULE.raw, "FPDFText_LoadFont", native)
    with pytest.raises(ValueError, match="total character map limit"):
        create_pdf(SPEC, font_bytes=bytes(data))


def test_http_font_upload_to_native_generation_and_current_download(file_client, monkeypatch):
    from types import SimpleNamespace

    from app.gateway.routers import uploads
    from deerflow.uploads import manager

    client, _, paths, runtime = file_client
    calls = []

    def acquire(thread_id, **identity):
        calls.append((thread_id, identity))
        return "local-font-http"

    monkeypatch.setattr(manager, "get_paths", lambda: paths)
    monkeypatch.setattr(uploads, "get_sandbox_provider", lambda: SimpleNamespace(acquire=acquire, get=lambda _: SimpleNamespace()))
    endpoint = "/api/threads/member-thread/uploads"
    uploaded = client.post(endpoint, files={"files": ("source.ttf", FONT, "font/ttf")})
    assert uploaded.status_code == 200, uploaded.text
    item = uploaded.json()["files"][0]
    assert item["virtual_path"] == "/mnt/user-data/uploads/source.ttf"
    assert (Path(runtime.state["thread_data"]["uploads_path"]) / "source.ttf").read_bytes() == FONT
    assert calls == [("member-thread", {"user_id": "user-a", "tenant_id": "tenant-a"})]
    for headers in [{"x-user": "user-b"}, {"x-tenant": "tenant-b"}]:
        assert client.post(endpoint, headers=headers, files={"files": ("denied.ttf", FONT, "font/ttf")}).status_code == 404
    assert len(calls) == 1
    result = office_pdf_tool.func(runtime, "create", output_path="/mnt/user-data/outputs/http-font.pdf", document=SPEC, font_path=item["virtual_path"])
    assert result["status"] == "ok"
    response = client.get("/api/threads/member-thread/artifacts/mnt/user-data/outputs/http-font.pdf?download=true")
    assert response.status_code == 200 and "Ελληνικά" in inspect_pdf(response.content)["pages"][0]["text"]
