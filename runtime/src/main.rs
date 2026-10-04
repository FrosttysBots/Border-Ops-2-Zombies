use blacklands_runtime::{MAX_BYTES, Pose, Stream, identifier};
use serde::Deserialize;
use serde_json::json;
use std::{
    env, fs,
    io::{self, BufRead, Read},
    net::UdpSocket,
    path::Path,
    time::{Duration, Instant},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Bootstrap {
    epoch: String,
    token: String,
}

fn write_json(path: &Path, value: serde_json::Value) -> io::Result<()> {
    let temp = path.with_extension("tmp");
    fs::write(&temp, serde_json::to_vec_pretty(&value)?)?;
    fs::rename(temp, path)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 4 {
        return Err(
            "Usage: blacklands-runtime ENDPOINT REPORT SECONDS (bootstrap on stdin)".into(),
        );
    }
    let seconds: u64 = args[3].parse()?;
    if !(1..=180).contains(&seconds) {
        return Err("Duration must be 1..180 seconds".into());
    }
    let mut line = String::new();
    io::stdin().lock().take(1025).read_line(&mut line)?;
    if line.len() > 1024 {
        return Err("Oversized bootstrap".into());
    }
    let bootstrap: Bootstrap = serde_json::from_str(&line)?;
    if !identifier(&bootstrap.epoch) || !identifier(&bootstrap.token) {
        return Err("Invalid bootstrap".into());
    }
    let endpoint = Path::new(&args[1]);
    let report = Path::new(&args[2]);
    let socket = UdpSocket::bind("127.0.0.1:0")?;
    socket.set_read_timeout(Some(Duration::from_millis(20)))?;
    write_json(
        endpoint,
        json!({"schema":1,"transport":"udp_loopback","host":"127.0.0.1",
        "port":socket.local_addr()?.port(),"epoch":bootstrap.epoch,"token":bootstrap.token,
        "capabilities":["bl2_pose_readonly"],"max_bytes":MAX_BYTES}),
    )?;
    println!("Read-only Rust bridge ready for {seconds}s; no gameplay command channel.");
    let start = Instant::now();
    let mut stream = Stream::default();
    let mut buffer = [0u8; MAX_BYTES + 1];
    let mut last_report = Instant::now() - Duration::from_secs(1);
    loop {
        let now = start.elapsed().as_millis() as u64;
        let finished = now >= seconds * 1000;
        if finished || last_report.elapsed() >= Duration::from_millis(250) {
            let latest = stream.latest.as_ref().map(|p| {
                json!({"session":p.session,"seq":p.seq,
                "origin":p.origin,"position":p.position,"angles":p.angles,"weapon":p.weapon})
            });
            let online = !finished && stream.online(now);
            write_json(
                report,
                json!({"schema":1,"epoch":bootstrap.epoch,"running":!finished,
                "transport":"udp_loopback","readonly":true,"online":online,
                "native_bl2_online":online && stream.latest.as_ref().is_some_and(|p| p.origin=="native_bl2"),
                "accepted":stream.received,"rejected":stream.rejected,"sequence_gaps":stream.sequence_gaps,
                "last_receive_age_ms":stream.latest.as_ref().map(|_| now.saturating_sub(stream.last_ms)),
                "latest":latest,"unsupported":["bo2_fast_transport","input","damage","loot","rendering","audio"]}),
            )?;
            last_report = Instant::now();
        }
        if finished {
            break;
        }
        match socket.recv_from(&mut buffer) {
            Ok((length, addr)) if addr.ip().is_loopback() => {
                match Pose::parse(&buffer[..length], &bootstrap.epoch, &bootstrap.token) {
                    Ok(p) => {
                        let ack = json!({"schema":1,"kind":"ack","epoch":p.epoch,
                            "session":p.session,"seq":p.seq,"sent_us":p.sent_us});
                        if stream.accept(p, addr, start.elapsed().as_millis() as u64) {
                            let _ = socket.send_to(&serde_json::to_vec(&ack)?, addr);
                        }
                    }
                    Err(_) => stream.rejected += 1,
                }
            }
            Ok(_) => stream.rejected += 1,
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut
                ) => {}
            // Windows returns WSAEMSGSIZE rather than truncating oversized datagrams.
            Err(e) if e.raw_os_error() == Some(10040) => stream.rejected += 1,
            Err(e) if e.raw_os_error() == Some(10054) => {}
            Err(e) => return Err(e.into()),
        }
    }
    // Retain the endpoint for diagnosis; without advancing replies it cannot be live.
    println!(
        "Capture finished: {} accepted, {} rejected.",
        stream.received, stream.rejected
    );
    Ok(())
}
