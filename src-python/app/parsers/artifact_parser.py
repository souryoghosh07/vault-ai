import io
import os
import socket
import tempfile
import xml.etree.ElementTree as ET
from typing import List

try:
    import Evtx.Evtx as evtx
    EVTX_AVAILABLE = True
except ImportError:
    EVTX_AVAILABLE = False

try:
    import dpkt
    DPKT_AVAILABLE = True
except ImportError:
    DPKT_AVAILABLE = False


def parse_evtx_records(file_bytes: bytes) -> List[str]:
    """Parses binary Windows Event Log (.evtx) files into normalized event strings."""
    if not EVTX_AVAILABLE:
        return ["[WARN]: python-evtx parser not installed. Ingesting raw buffer."]

    temp_path = None
    records = []
    try:
        with tempfile.NamedTemporaryFile(suffix=".evtx", delete=False) as tf:
            tf.write(file_bytes)
            temp_path = tf.name

        with evtx.Evtx(temp_path) as log:
            for idx, record in enumerate(log.records()):
                try:
                    xml_str = record.xml()
                    root = ET.fromstring(xml_str)
                    ns = {"ns": "http://schemas.microsoft.com/win/2004/08/events/event"}

                    event_id = root.findtext(".//ns:EventID", default="N/A", namespaces=ns)
                    time_created = "N/A"
                    time_elem = root.find(".//ns:TimeCreated", namespaces=ns)
                    if time_elem is not None and "SystemTime" in time_elem.attrib:
                        time_created = time_elem.attrib["SystemTime"]

                    computer = root.findtext(".//ns:Computer", default="N/A", namespaces=ns)
                    provider = "N/A"
                    provider_elem = root.find(".//ns:Provider", namespaces=ns)
                    if provider_elem is not None and "Name" in provider_elem.attrib:
                        provider = provider_elem.attrib["Name"]

                    # Extract EventData key-value pairs
                    data_items = []
                    for data in root.findall(".//ns:EventData/ns:Data", namespaces=ns):
                        key = data.attrib.get("Name", "Data")
                        val = data.text or ""
                        data_items.append(f"{key}={val}")

                    data_summary = "; ".join(data_items[:12]) if data_items else "No EventData"
                    record_line = (
                        f"[EVTX Record #{record.record_num()}] Time: {time_created} | "
                        f"EventID: {event_id} | Provider: {provider} | Computer: {computer} | {data_summary}"
                    )
                    records.append(record_line)
                except Exception as ex:
                    records.append(f"[EVTX Record #{record.record_num()}] Raw Parse Error: {ex}")

                # Safeguard against massive EVTX dumps flooding local context
                if len(records) >= 500:
                    records.append("[NOTE]: Truncated at 500 event records for local processing.")
                    break
    except Exception as e:
        records.append(f"[ERROR]: Failed to parse EVTX file: {e}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    return records


def parse_pcap_packets(file_bytes: bytes) -> List[str]:
    """Parses network packet captures (.pcap, .pcapng) using dpkt into flow/HTTP summaries."""
    if not DPKT_AVAILABLE:
        return ["[WARN]: dpkt parser not installed. Ingesting raw buffer."]

    records = []
    f = io.BytesIO(file_bytes)
    reader = None

    # Try standard PCAP first, fall back to PCAPNG
    try:
        reader = dpkt.pcap.Reader(f)
    except Exception:
        f.seek(0)
        try:
            reader = dpkt.pcapng.Reader(f)
        except Exception as e:
            return [f"[ERROR]: Could not parse as PCAP or PCAPNG: {e}"]

    for idx, (ts, buf) in enumerate(reader):
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            # Only process IPv4 / IPv6 packets
            if isinstance(eth.data, dpkt.ip.IP):
                ip = eth.data
                src_ip = socket.inet_ntoa(ip.src)
                dst_ip = socket.inet_ntoa(ip.dst)
                proto_name = "IP"

                if isinstance(ip.data, dpkt.tcp.TCP):
                    tcp = ip.data
                    proto_name = f"TCP {src_ip}:{tcp.sport} -> {dst_ip}:{tcp.dport}"
                    payload_info = ""

                    # Inspect common web/API ports for HTTP
                    if tcp.dport in (80, 443, 8000, 8080, 8443, 9060) or tcp.sport in (80, 443, 8000, 8080, 8443, 9060):
                        try:
                            http = dpkt.http.Request(tcp.data)
                            auth_header = http.headers.get("authorization", "None")
                            user_agent = http.headers.get("user-agent", "None")
                            payload_info = f" | HTTP {http.method} {http.uri} [Auth: {auth_header}] [UA: {user_agent}]"
                        except Exception:
                            if tcp.data:
                                payload_info = f" | PayloadLen={len(tcp.data)}"
                    elif tcp.data:
                        payload_info = f" | PayloadLen={len(tcp.data)}"

                    records.append(f"[Packet #{idx + 1}] TS={ts:.3f} | {proto_name}{payload_info}")

                elif isinstance(ip.data, dpkt.udp.UDP):
                    udp = ip.data
                    proto_name = f"UDP {src_ip}:{udp.sport} -> {dst_ip}:{udp.dport}"
                    dns_info = ""
                    if udp.dport == 53 or udp.sport == 53:
                        try:
                            dns = dpkt.dns.DNS(udp.data)
                            queries = [q.name for q in dns.qd]
                            dns_info = f" | DNS Queries: {', '.join(queries)}"
                        except Exception:
                            pass
                    records.append(f"[Packet #{idx + 1}] TS={ts:.3f} | {proto_name}{dns_info}")
                else:
                    records.append(f"[Packet #{idx + 1}] TS={ts:.3f} | Protocol={ip.p} {src_ip} -> {dst_ip}")

            elif isinstance(eth.data, dpkt.ip6.IP6):
                ip6 = eth.data
                src_ip = socket.inet_ntop(socket.AF_INET6, ip6.src)
                dst_ip = socket.inet_ntop(socket.AF_INET6, ip6.dst)
                records.append(f"[Packet #{idx + 1}] TS={ts:.3f} | IPv6 {src_ip} -> {dst_ip}")

        except Exception:
            continue

        if len(records) >= 800:
            records.append("[NOTE]: Truncated at 800 packets for local processing.")
            break

    return records or ["[INFO]: No IP packets decoded in capture."]


def parse_text_logs(file_bytes: bytes) -> List[str]:
    """Parses plain text, syslog, web server, and Kong API gateway logs."""
    text = file_bytes.decode("utf-8", errors="replace")
    raw_lines = text.splitlines()
    records = []
    for idx, line in enumerate(raw_lines, 1):
        stripped = line.strip()
        if stripped:
            records.append(f"[Line {idx}] {stripped}")

    return records


def parse_pdf_document(file_bytes: bytes, filename: str) -> List[str]:
    """Parses PDF forensic reports or threat advisories using IBM Docling."""
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat, DocumentStream
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    except ImportError:
        return ["[WARN]: Docling not installed or available for PDF processing."]

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.ocr_options = RapidOcrOptions()

    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)},
    )

    stream = DocumentStream(name=filename, stream=io.BytesIO(file_bytes))
    result = converter.convert(stream)

    records = []
    for item, _ in result.document.iterate_items():
        if not item.prov:
            continue
        page_no = item.prov[0].page_no
        try:
            content = item.export_to_markdown(result.document).strip()
        except AttributeError:
            content = getattr(item, "text", "").strip()

        if content:
            records.append(f"[Page {page_no}] {content}")

    return records


def parse_security_artifact(file_bytes: bytes, filename: str) -> List[str]:
    """Unified entrypoint that dispatches to the appropriate forensic artifact parser."""
    lower_name = filename.lower()

    if lower_name.endswith(".evtx"):
        return parse_evtx_records(file_bytes)
    elif lower_name.endswith((".pcap", ".pcapng", ".cap")):
        return parse_pcap_packets(file_bytes)
    elif lower_name.endswith(".pdf"):
        return parse_pdf_document(file_bytes, filename)
    else:
        # Default handler for .log, .txt, .json, .csv, .xml, .syslog, etc.
        return parse_text_logs(file_bytes)
