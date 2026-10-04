//! Read-only local pose boundary. No game pointers, commands, damage or input.
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::net::SocketAddr;

pub const MAX_BYTES: usize = 8192;
pub const STALE_MS: u64 = 2000;

pub fn identifier(s: &str) -> bool {
    s.len() == 32
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Pose {
    pub schema: u32,
    pub kind: String,
    pub source: String,
    pub origin: String,
    pub epoch: String,
    pub token: String,
    pub session: String,
    pub seq: u64,
    pub sent_us: u64,
    pub position: [f64; 3],
    pub angles: [f64; 3],
    pub weapon: Option<String>,
}

impl Pose {
    pub fn parse(bytes: &[u8], epoch: &str, token: &str) -> Result<Self, &'static str> {
        if bytes.len() > MAX_BYTES {
            return Err("oversized");
        }
        let p: Self = serde_json::from_slice(bytes).map_err(|_| "malformed")?;
        if p.schema != 1
            || p.kind != "pose"
            || p.source != "bl2"
            || !matches!(p.origin.as_str(), "native_bl2" | "synthetic_test")
            || p.epoch != epoch
            || p.token != token
            || !identifier(&p.session)
            || p.seq == 0
            || p.seq > (1u64 << 53) - 1
            || p.sent_us > (1u64 << 53) - 1
            || p.position
                .iter()
                .chain(p.angles.iter())
                .any(|v| !v.is_finite() || v.abs() > 100_000_000.0)
            || p.weapon.as_ref().is_some_and(|s| s.len() > 512)
        {
            return Err("invalid_contract");
        }
        Ok(p)
    }
}

#[derive(Default)]
pub struct Stream {
    pub latest: Option<Pose>,
    endpoint: Option<SocketAddr>,
    retired: HashSet<String>,
    pub received: u64,
    pub rejected: u64,
    pub sequence_gaps: u64,
    pub session_samples: u64,
    pub last_ms: u64,
}

impl Stream {
    pub fn accept(&mut self, p: Pose, addr: SocketAddr, now_ms: u64) -> bool {
        let mut gap = 0;
        let mut switched = self.latest.is_none();
        if let Some(old) = &self.latest {
            if old.session == p.session {
                if self.endpoint != Some(addr)
                    || old.origin != p.origin
                    || p.seq <= old.seq
                    || p.sent_us < old.sent_us
                {
                    self.rejected += 1;
                    return false;
                }
                gap = p.seq - old.seq - 1;
            } else {
                if now_ms.saturating_sub(self.last_ms) <= STALE_MS
                    || self.retired.contains(&p.session)
                    || self.retired.len() >= 64
                {
                    self.rejected += 1;
                    return false;
                }
                self.retired.insert(old.session.clone());
                switched = true;
            }
        }
        if switched {
            self.session_samples = 0;
        }
        self.endpoint = Some(addr);
        self.session_samples += 1;
        self.received += 1;
        self.sequence_gaps += gap;
        self.last_ms = now_ms;
        self.latest = Some(p);
        true
    }

    pub fn online(&self, now_ms: u64) -> bool {
        self.session_samples >= 2 && now_ms.saturating_sub(self.last_ms) <= STALE_MS
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pose(seq: u64) -> Pose {
        Pose {
            schema: 1,
            kind: "pose".into(),
            source: "bl2".into(),
            origin: "synthetic_test".into(),
            epoch: "a".repeat(32),
            token: "b".repeat(32),
            session: "c".repeat(32),
            seq,
            sent_us: seq * 100,
            position: [0.; 3],
            angles: [0.; 3],
            weapon: None,
        }
    }
    fn addr() -> SocketAddr {
        "127.0.0.1:54321".parse().unwrap()
    }
    #[test]
    fn rejects_commands_wrong_tokens_versions_and_nonfinite_fields() {
        let p = pose(1);
        let bytes = serde_json::to_vec(&p).unwrap();
        assert!(Pose::parse(&bytes, &p.epoch, &p.token).is_ok());
        assert!(Pose::parse(&bytes, &p.epoch, "wrong").is_err());
        for replacement in [
            serde_json::json!({"kind":"apply_damage"}),
            serde_json::json!({"schema":2}),
            serde_json::json!({"position":[null,0,0]}),
            serde_json::json!({"command":"fire"}),
        ] {
            let mut value = serde_json::to_value(&p).unwrap();
            for (key, v) in replacement.as_object().unwrap() {
                value[key] = v.clone();
            }
            assert!(Pose::parse(&serde_json::to_vec(&value).unwrap(), &p.epoch, &p.token).is_err());
        }
        assert!(Pose::parse(&vec![0; MAX_BYTES + 1], &p.epoch, &p.token).is_err());
    }
    #[test]
    fn duplicates_and_reordering_cannot_keep_peer_online() {
        let mut s = Stream::default();
        assert!(s.accept(pose(1), addr(), 0));
        assert!(!s.online(0));
        assert!(s.accept(pose(3), addr(), 10));
        assert!(s.online(10));
        assert_eq!(s.sequence_gaps, 1);
        assert!(!s.accept(pose(2), addr(), 1500));
        assert!(!s.accept(pose(3), addr(), 1900));
        assert!(!s.online(2011));
    }
    #[test]
    fn restarts_require_stale_old_session_and_two_fresh_samples() {
        let mut s = Stream::default();
        s.accept(pose(1), addr(), 0);
        let mut p = pose(1);
        p.session = "d".repeat(32);
        assert!(!s.accept(p.clone(), addr(), 1));
        assert!(s.accept(p.clone(), addr(), 2001));
        assert!(!s.online(2001));
        p.seq = 2;
        assert!(s.accept(p, addr(), 2010));
        assert!(s.online(2010));
        assert!(!s.accept(pose(5), addr(), 5000));
    }
    #[test]
    fn rejects_endpoint_origin_and_clock_changes_inside_session() {
        let mut s = Stream::default();
        s.accept(pose(2), addr(), 0);
        assert!(!s.accept(pose(3), "127.0.0.1:54322".parse().unwrap(), 1));
        let mut p = pose(3);
        p.origin = "native_bl2".into();
        assert!(!s.accept(p, addr(), 1));
        let mut p = pose(3);
        p.sent_us = 1;
        assert!(!s.accept(p, addr(), 1));
    }
}
