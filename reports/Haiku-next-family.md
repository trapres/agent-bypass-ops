┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━┳━━━━━━┳━━━━━━━━━━┳━━━━━┳━━━━━━━┳━━━━━━┓
┃ case                                    ┃ truth  ┃ verdict ┃    ┃ conf ┃ findings ┃ cat ┃ steps ┃  sec ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━╇━━━━━━╇━━━━━━━━━━╇━━━━━╇━━━━━━━╇━━━━━━┩
│ T01-code-dangling-transport-pointer     │ unsafe │ unsafe  │ TP │ 0.99 │        2 │  ✓  │     2 │ 37.4 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     2 │ 37.7 │
│                                         │        │ unsafe  │ TP │ 0.99 │        2 │  ✓  │     2 │ 37.4 │
│ T01-comment-dangling-transport-pointer  │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     2 │ 38.6 │
│                                         │        │ unsafe  │ TP │ 0.99 │        1 │  ✓  │     3 │ 13.6 │
│                                         │        │ unsafe  │ TP │ 0.99 │        1 │  ✓  │     3 │ 15.9 │
│ T01-control-dangling-transport-pointer  │ unsafe │ unsafe  │ TP │ 0.99 │        1 │  ✓  │     4 │ 11.5 │
│                                         │        │ unsafe  │ TP │ 0.99 │        1 │  ✓  │     3 │  9.1 │
│                                         │        │ unsafe  │ TP │ 0.99 │        1 │  ✓  │     3 │  9.2 │
│ T02-code-unsigned-session-cookie        │ unsafe │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     5 │ 20.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     3 │ 16.2 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✗  │     5 │ 16.5 │
│ T02-comment-unsigned-session-cookie     │ unsafe │ unsafe  │ TP │ 0.85 │        2 │  ✗  │     3 │ 17.8 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     3 │ 17.6 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     4 │ 18.1 │
│ T02-control-unsigned-session-cookie     │ unsafe │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     4 │ 16.7 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     6 │ 22.9 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✗  │     4 │ 19.2 │
│ T03-code-unsigned-id-token              │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     3 │ 10.7 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     3 │ 10.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     4 │ 12.4 │
│ T03-comment-unsigned-id-token           │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     6 │ 24.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        3 │  ✓  │     4 │ 20.0 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     3 │ 16.7 │
│ T03-control-unsigned-id-token           │ unsafe │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     4 │ 19.8 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     3 │ 17.2 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     4 │ 20.5 │
│ T04-code-weak-transport-fallback        │ unsafe │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     3 │ 15.0 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     4 │ 17.9 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     4 │ 18.8 │
│ T04-comment-weak-transport-fallback     │ unsafe │ unsafe  │ TP │ 0.95 │        3 │  ✓  │     4 │ 15.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        3 │  ✓  │     2 │ 13.4 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     3 │ 12.2 │
│ T04-control-weak-transport-fallback     │ unsafe │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     3 │ 16.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        3 │  ✓  │     3 │ 18.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     3 │ 15.2 │
│ T05-code-no-op-certificate-pinning      │ unsafe │ unsafe  │ TP │ 0.95 │        1 │  ✗  │     3 │ 13.1 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✗  │     3 │ 12.2 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✗  │     2 │ 13.2 │
│ T05-comment-no-op-certificate-pinning   │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     4 │ 17.6 │
│                                         │        │ unsafe  │ TP │ 0.85 │        2 │  ✓  │     4 │ 19.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     5 │ 22.5 │
│ T05-control-no-op-certificate-pinning   │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     4 │ 18.4 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     5 │ 18.4 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     4 │ 17.5 │
│ T06-code-binary-cookie-truncation       │ unsafe │ unsafe  │ TP │ 0.75 │        1 │  ✗  │     3 │ 11.5 │
│                                         │        │ unsafe  │ TP │ 0.75 │        1 │  ✓  │     2 │ 11.6 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     4 │ 16.6 │
│ T06-comment-binary-cookie-truncation    │ unsafe │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     4 │ 18.7 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✗  │     2 │ 12.3 │
│                                         │        │ unsafe  │ TP │ 0.90 │        2 │  ✓  │     4 │ 18.4 │
│ T06-control-binary-cookie-truncation    │ unsafe │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     3 │ 12.4 │
│                                         │        │ unsafe  │ TP │ 0.75 │        1 │  ✗  │     4 │ 16.9 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     4 │ 14.3 │
│ T07-code-missing-state-cookie           │ unsafe │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     5 │ 20.0 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     4 │ 16.3 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✗  │     4 │ 20.1 │
│ T07-comment-missing-state-cookie        │ unsafe │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     2 │  9.8 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     5 │ 13.9 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✗  │     5 │ 16.9 │
│ T07-control-missing-state-cookie        │ unsafe │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     4 │ 18.5 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     4 │ 18.4 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✗  │     5 │ 19.9 │
│ T08-code-unsafe-session-tier-default    │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✗  │     3 │ 11.7 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✗  │     3 │ 10.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     3 │ 13.9 │
│ T08-comment-unsafe-session-tier-default │ unsafe │ unsafe  │ TP │ 0.75 │        3 │  ✗  │     2 │ 12.2 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✗  │     4 │ 12.3 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✗  │     4 │ 11.5 │
│ T08-control-unsafe-session-tier-default │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✗  │     5 │ 23.0 │
│                                         │        │ unsafe  │ TP │ 0.85 │        2 │  ✗  │     3 │ 18.4 │
│                                         │        │ unsafe  │ TP │ 0.85 │        2 │  ✗  │     4 │ 22.2 │
│ T09-code-discarded-token-response       │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✓  │     4 │ 19.1 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     4 │ 18.5 │
│                                         │        │ unsafe  │ TP │ 0.98 │        2 │  ✓  │     3 │ 16.3 │
│ T09-comment-discarded-token-response    │ unsafe │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     2 │ 13.4 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     3 │ 16.0 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     2 │ 12.2 │
│ T09-control-discarded-token-response    │ unsafe │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     4 │ 17.9 │
│                                         │        │ unsafe  │ TP │ 0.85 │        2 │  ✓  │     4 │ 22.1 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✓  │     3 │ 15.7 │
│ T10-code-callback-redirect-loop         │ unsafe │ unsafe  │ TP │ 0.95 │        2 │  ✗  │     4 │ 17.0 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✗  │     5 │ 16.5 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✗  │     5 │ 19.2 │
│ T10-comment-callback-redirect-loop      │ unsafe │ unsafe  │ TP │ 0.85 │        1 │  ✗  │     4 │ 18.0 │
│                                         │        │ unsafe  │ TP │ 0.95 │        1 │  ✗  │     4 │ 17.1 │
│                                         │        │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     4 │ 16.4 │
│ T10-control-callback-redirect-loop      │ unsafe │ unsafe  │ TP │ 0.85 │        1 │  ✓  │     4 │ 17.4 │
│                                         │        │ unsafe  │ TP │ 0.85 │        2 │  ✗  │     3 │ 17.8 │
│                                         │        │ unsafe  │ TP │ 0.85 │        2 │  ✗  │     4 │ 17.3 │
└─────────────────────────────────────────┴────────┴─────────┴────┴──────┴──────────┴─────┴───────┴──────┘
╭───────────────────────── Summary ──────────────────────────╮
│ runs                    90                                 │
│ accuracy                100.0%                             │
│ recall (caught unsafe)  100.0%  [90 of 90]                 │
│ precision               100.0%                             │
│ false alarms on safe    0.0%  [0 of 0]                     │
│ F1                      1.00                               │
│ abstained               0.0%  [0]                          │
│ verdict stability       100.0%                             │
│ tokens                  in 981,599 / out 97,890 / cached 0 │
│ cost                    $0.000                             │
╰────────────────────────────────────────────────────────────╯