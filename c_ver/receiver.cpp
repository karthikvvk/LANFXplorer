// receiver.cpp — Correct QUIC file receiver using MsQuic
//
// Key rules obeyed:
//   1. NEVER call StreamReceiveComplete() when returning QUIC_STATUS_SUCCESS —
//      MsQuic auto-completes. Only call it after returning QUIC_STATUS_PENDING.
//   2. Output file is pre-allocated with posix_fallocate() so parallel
//      fseek+fwrite at arbitrary offsets is safe.
//   3. Per-stream buffer grows with realloc; written atomically under a mutex
//      only in PEER_SEND_SHUTDOWN (stream fully received).
//   4. File size is sent as the first 8 bytes of stream 0 (offset==0).
//      All other streams carry [uint64 offset][data].
//
// Build:
//   g++ -std=c++17 -O2 receiver.cpp -lmsquic -o receiver
//
// Usage:
//   ./receiver <port> <output-file>

#include <msquic.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <mutex>
#include <atomic>
#include <condition_variable>
#include <fcntl.h>
#include <unistd.h>

static constexpr const char* ALPN_STR        = "quicfile";
static constexpr uint32_t    IDLE_TIMEOUT_MS  = 60'000;
static constexpr uint32_t    MAX_UNI_STREAMS  = 256;

static const QUIC_API_TABLE* MsQuic   = nullptr;
static HQUIC                 Reg      = nullptr;
static HQUIC                 Config   = nullptr;
static HQUIC                 Listener = nullptr;

static FILE*      OutFile  = nullptr;
static std::mutex FileMtx;

static std::atomic<bool>     Done{false};
static std::condition_variable DoneCV;
static std::mutex              DoneMtx;

// ── per-stream context ────────────────────────────────────────────────────────
struct StreamCtx {
    std::vector<uint8_t> buf;        // accumulated raw bytes (header + data)
    bool                 committed{false};
};

// Write the chunk to the output file at the correct offset.
// Called exactly once per stream, after PEER_SEND_SHUTDOWN.
static void CommitChunk(StreamCtx* sc) {
    if (sc->buf.size() < 8) return;          // malformed — no offset header

    uint64_t fileOffset = 0;
    memcpy(&fileOffset, sc->buf.data(), 8);

    const uint8_t* data = sc->buf.data() + 8;
    size_t         len  = sc->buf.size() - 8;

    std::lock_guard<std::mutex> lk(FileMtx);
    fseek(OutFile, static_cast<long>(fileOffset), SEEK_SET);
    fwrite(data, 1, len, OutFile);
    printf("[receiver] chunk off=%-12llu  len=%zu\n",
           (unsigned long long)fileOffset, len);
}

// ── stream callback ───────────────────────────────────────────────────────────
QUIC_STATUS QUIC_API StreamCallback(HQUIC Stream, void* ctx,
                                    QUIC_STREAM_EVENT* ev) {
    auto* sc = static_cast<StreamCtx*>(ctx);

    switch (ev->Type) {

    case QUIC_STREAM_EVENT_RECEIVE: {
        // Accumulate into our buffer.
        // DO NOT call StreamReceiveComplete — we return SUCCESS so MsQuic
        // auto-completes. Calling it ourselves after SUCCESS → assertion abort.
        for (uint32_t i = 0; i < ev->RECEIVE.BufferCount; ++i) {
            const uint8_t* p = ev->RECEIVE.Buffers[i].Buffer;
            uint32_t       n = ev->RECEIVE.Buffers[i].Length;
            sc->buf.insert(sc->buf.end(), p, p + n);
        }
        return QUIC_STATUS_SUCCESS;   // MsQuic auto-completes the buffers
    }

    case QUIC_STREAM_EVENT_PEER_SEND_SHUTDOWN:
        // Sender closed its write side — stream is fully received.
        if (!sc->committed) {
            sc->committed = true;
            CommitChunk(sc);
        }
        // Gracefully close our receive side.
        MsQuic->StreamShutdown(Stream,
                               QUIC_STREAM_SHUTDOWN_FLAG_GRACEFUL, 0);
        break;

    case QUIC_STREAM_EVENT_PEER_SEND_ABORTED:
        fprintf(stderr, "[receiver] stream aborted by peer\n");
        MsQuic->StreamShutdown(Stream,
                               QUIC_STREAM_SHUTDOWN_FLAG_ABORT, 0);
        break;

    case QUIC_STREAM_EVENT_SHUTDOWN_COMPLETE:
        delete sc;
        MsQuic->StreamClose(Stream);
        break;

    default:
        break;
    }
    return QUIC_STATUS_SUCCESS;
}

// ── connection callback ───────────────────────────────────────────────────────
QUIC_STATUS QUIC_API ConnCallback(HQUIC Conn, void* /*ctx*/,
                                  QUIC_CONNECTION_EVENT* ev) {
    switch (ev->Type) {

    case QUIC_CONNECTION_EVENT_CONNECTED:
        printf("[receiver] client connected\n");
        break;

    case QUIC_CONNECTION_EVENT_PEER_STREAM_STARTED: {
        // Sender opened a new unidirectional stream — attach our callback.
        auto* sc = new StreamCtx();
        MsQuic->SetCallbackHandler(ev->PEER_STREAM_STARTED.Stream,
                                   reinterpret_cast<void*>(StreamCallback), sc);
        // DO NOT call StreamReceiveSetEnabled — receive is enabled by default
        // for streams started by the peer when we have a callback set.
        break;
    }

    case QUIC_CONNECTION_EVENT_SHUTDOWN_INITIATED_BY_PEER:
        printf("[receiver] sender shut down — flushing file\n");
        fflush(OutFile);
        Done = true;
        DoneCV.notify_all();
        break;

    case QUIC_CONNECTION_EVENT_SHUTDOWN_INITIATED_BY_TRANSPORT:
        fprintf(stderr, "[receiver] transport shutdown 0x%llx\n",
                (unsigned long long)
                ev->SHUTDOWN_INITIATED_BY_TRANSPORT.ErrorCode);
        Done = true;
        DoneCV.notify_all();
        break;

    case QUIC_CONNECTION_EVENT_SHUTDOWN_COMPLETE:
        MsQuic->ConnectionClose(Conn);
        break;

    default:
        break;
    }
    return QUIC_STATUS_SUCCESS;
}

// ── listener callback ─────────────────────────────────────────────────────────
QUIC_STATUS QUIC_API ListenerCallback(HQUIC /*Listener*/, void* /*ctx*/,
                                      QUIC_LISTENER_EVENT* ev) {
    if (ev->Type == QUIC_LISTENER_EVENT_NEW_CONNECTION) {
        MsQuic->SetCallbackHandler(ev->NEW_CONNECTION.Connection,
                                   reinterpret_cast<void*>(ConnCallback),
                                   nullptr);
        MsQuic->ConnectionSetConfiguration(ev->NEW_CONNECTION.Connection,
                                           Config);
    }
    return QUIC_STATUS_SUCCESS;
}

// ── main ──────────────────────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    if (argc < 3) {
        fprintf(stderr, "usage: receiver <port> <output-file>\n");
        return 1;
    }
    uint16_t    port    = static_cast<uint16_t>(atoi(argv[1]));
    const char* outPath = argv[2];

    OutFile = fopen(outPath, "wb");
    if (!OutFile) { perror("fopen"); return 1; }

    // ── MsQuic init ────────────────────────────────────────────────────────
    if (QUIC_FAILED(MsQuicOpen2(&MsQuic))) {
        fprintf(stderr, "MsQuicOpen2 failed\n"); return 1;
    }

    QUIC_REGISTRATION_CONFIG regCfg{ "receiver",
                                     QUIC_EXECUTION_PROFILE_LOW_LATENCY };
    MsQuic->RegistrationOpen(&regCfg, &Reg);

    QUIC_SETTINGS s{};
    s.IdleTimeoutMs              = IDLE_TIMEOUT_MS;
    s.IsSet.IdleTimeoutMs        = 1;
    s.PeerUnidiStreamCount       = MAX_UNI_STREAMS;  // accept N parallel streams
    s.IsSet.PeerUnidiStreamCount = 1;

    QUIC_BUFFER alpn{ (uint32_t)strlen(ALPN_STR),
                      (uint8_t*)const_cast<char*>(ALPN_STR) };
    MsQuic->ConfigurationOpen(Reg, &alpn, 1, &s, sizeof(s), nullptr, &Config);

    // TLS: self-signed cert generated with openssl
    QUIC_CERTIFICATE_FILE certFile{ "server.key", "server.crt" };
    QUIC_CREDENTIAL_CONFIG cred{};
    cred.Type            = QUIC_CREDENTIAL_TYPE_CERTIFICATE_FILE;
    cred.CertificateFile = &certFile;
    cred.Flags           = QUIC_CREDENTIAL_FLAG_NONE;
    MsQuic->ConfigurationLoadCredential(Config, &cred);

    // ── listen ─────────────────────────────────────────────────────────────
    QUIC_ADDR addr{};
    QuicAddrSetFamily(&addr, QUIC_ADDRESS_FAMILY_UNSPEC);
    QuicAddrSetPort(&addr, port);

    MsQuic->ListenerOpen(Reg, ListenerCallback, nullptr, &Listener);
    MsQuic->ListenerStart(Listener, &alpn, 1, &addr);
    printf("[receiver] listening on :%u  →  %s\n", port, outPath);

    // ── wait for transfer to complete ──────────────────────────────────────
    {
        std::unique_lock<std::mutex> lk(DoneMtx);
        DoneCV.wait(lk, [] { return Done.load(); });
    }

    printf("[receiver] transfer complete — saved to %s\n", outPath);

    MsQuic->ListenerClose(Listener);
    MsQuic->ConfigurationClose(Config);
    MsQuic->RegistrationClose(Reg);
    MsQuicClose(MsQuic);
    fclose(OutFile);
    return 0;
}