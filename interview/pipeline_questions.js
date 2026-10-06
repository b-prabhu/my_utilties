/* Round 1 — theory question bank.
   Each candidate draws one question per topic from the pool that matches their
   competency stream and level. Recycling advances the offset within that pool,
   so a fresh question appears without losing notes already keyed to the old one.

   q  question put to the candidate
   a  model answer — what a strong reply covers
   f  follow-up to push with, or the weak answer to watch for
   s  streams it suits: "all", or any of dotnet / java / node / support
   l  level: "any", "senior" (leads and consultants) or "mid"           */

var QTOPICS = [
  {k:"design",      h:"System design patterns"},
  {k:"integration", h:"Integration patterns"},
  {k:"security",    h:"Security considerations"},
  {k:"scale",       h:"Scalability"},
  {k:"tenancy",     h:"Multi-tenancy"},
  {k:"infra",       h:"Infrastructure"},
  {k:"arch",        h:"Architecture"}
];

/* Competency stream per candidate, taken from what the CV actually shows
   rather than the role the vendor applied them against. */
var QSTREAM = {
  1:{s:"dotnet", l:"senior"},  2:{s:"dotnet", l:"senior"},  3:{s:"dotnet", l:"senior"},
  4:{s:"dotnet", l:"senior"},  5:{s:"dotnet", l:"senior"},  6:{s:"java",   l:"senior"},
  7:{s:"node",   l:"senior"},  8:{s:"dotnet", l:"senior"},  9:{s:"java",   l:"senior"},
  10:{s:"java",  l:"senior"}, 11:{s:"node",   l:"senior"}, 12:{s:"node",   l:"senior"},
  13:{s:"support", l:"mid"},  14:{s:"support", l:"mid"},   15:{s:"support", l:"mid"},
  16:{s:"support", l:"mid"},  17:{s:"java",   l:"mid"},
  /* Added 6 Oct 2026 */
  18:{s:"java",  l:"senior"}, 19:{s:"java",   l:"senior"}, 20:{s:"java", l:"senior"},
  21:{s:"node",  l:"mid"},    22:{s:"java",   l:"senior"}
};

var QBANK = [

/* ---------------------------------------------------- system design patterns */
{k:"design", s:"all", l:"any", id:"d1",
 q:"Explain CQRS. What problem does it solve, and what does it cost you?",
 a:"Command Query Responsibility Segregation splits the write model from the read model so each can be shaped for its own job — writes enforce invariants and stay normalised, reads are denormalised and shaped for the screen that needs them. It pays off when read and write loads differ sharply, when reads need many different projections, or when write-side validation is complex. The cost is two models to keep in step: if the read side is updated asynchronously you inherit eventual consistency, so the UI must tolerate reading its own write late, and you need a rebuild path for projections.",
 f:"Weak answers describe it as ‘separate read and write methods’. Push on what happens immediately after a command when the read model has not caught up, and how they would rebuild a projection that has drifted."},

{k:"design", s:"all", l:"any", id:"d2",
 q:"When would you choose an event-driven design over request/response, and what do you give up?",
 a:"Event-driven suits work that is asynchronous by nature, fans out to several consumers, or must survive a downstream being unavailable — the producer records that something happened and moves on. It decouples producers from consumers and smooths load spikes. You give up the straight-line traceability of a call stack: debugging spans a broker, ordering is only guaranteed within a partition or session, delivery is at-least-once so consumers must be idempotent, and there is no simple synchronous error to return to the caller.",
 f:"Listen for idempotency and ordering unprompted. A candidate who only lists benefits has not run one in production."},

{k:"design", s:"all", l:"senior", id:"d3",
 q:"What is the Saga pattern, and how does choreography differ from orchestration?",
 a:"A saga keeps a business transaction consistent across services without a distributed transaction: each step commits locally and publishes an event, and failure triggers compensating actions that semantically undo earlier steps rather than rolling back. Choreography has each service react to events with no central coordinator — simple and loosely coupled, but the overall flow is implicit and hard to follow. Orchestration puts one coordinator in charge of calling each step and running compensations — the flow is explicit and easier to reason about and monitor, at the cost of a component that knows about everyone.",
 f:"Ask for a compensating action that is genuinely hard, such as an e-mail already sent or a payment already captured. Good candidates talk about semantic compensation rather than rollback."},

{k:"design", s:"all", l:"any", id:"d4",
 q:"Explain the circuit breaker pattern and how it differs from a retry.",
 a:"A retry re-attempts a failed call in the hope it was transient; a circuit breaker watches the failure rate and, past a threshold, stops calling the dependency at all for a cooling period, failing fast and letting it recover. After the timeout it half-opens, lets a trial call through, and closes on success. The two are complementary but retries alone are dangerous — they multiply load on a service that is already struggling, which is how a slow dependency becomes an outage. Retries need backoff, jitter, and a cap, and should only apply to idempotent operations.",
 f:"Ask what happens when every instance retries the same failing dependency at once. Look for the retry storm and for jitter."},

{k:"design", s:"all", l:"senior", id:"d5",
 q:"What is the outbox pattern and what failure does it prevent?",
 a:"Writing to your database and publishing to a broker are two separate systems, so a crash between them either loses the message or publishes an event for a transaction that rolled back. The outbox pattern writes the event into an outbox table inside the same local transaction as the state change, and a separate relay reads that table and publishes to the broker, marking rows as sent. The state change and the intent to publish commit atomically; the relay gives at-least-once delivery, so consumers still need to be idempotent.",
 f:"A candidate who says ‘use a distributed transaction’ or ‘publish first, then save’ has not hit this in production. Ask how the relay avoids publishing twice after its own crash."},

{k:"design", s:"dotnet", l:"any", id:"d6",
 q:"How do the repository and unit-of-work patterns relate, and is a repository over Entity Framework worth it?",
 a:"A repository abstracts a collection of aggregates behind a domain-shaped interface; unit of work tracks changes across repositories and commits them as one transaction. DbContext is already both — it tracks changes and SaveChanges is the unit of work — so wrapping it in a generic repository usually adds a layer that leaks IQueryable and buys little. The defensible reasons are keeping persistence concerns out of the domain, expressing queries in domain language, and making tests independent of EF, not ‘so we can swap the database’.",
 f:"The honest answer names the over-abstraction. Be wary of a rehearsed ‘it lets us swap out the ORM’, which almost never happens."},

{k:"design", s:"java", l:"any", id:"d7",
 q:"How does dependency injection work in Spring, and what problems do singleton-scoped beans create?",
 a:"Spring's container instantiates beans, resolves their dependencies and injects them, with constructor injection preferred because it makes dependencies explicit and allows final fields. The default scope is singleton — one instance per application context — so any mutable field on a bean is shared across every request thread and becomes a race. Request- or prototype-scoped beans, or simply keeping beans stateless and passing state as parameters, avoid it; injecting a shorter-scoped bean into a singleton needs a proxy or a provider.",
 f:"Ask what happens if they add a mutable field to a @Service. If they do not immediately see the concurrency problem, that is a gap."},

{k:"design", s:"node", l:"any", id:"d8",
 q:"Node runs your JavaScript on a single thread. What does that mean for how you design a service?",
 a:"One thread runs the event loop, so any CPU-bound work — heavy JSON transforms, crypto, image work, synchronous file reads — blocks every other request on that process. I/O is fine because it is delegated to the platform and resumed via callbacks. So you keep handlers non-blocking, push CPU-heavy work to worker threads, a queue, or a separate service, and scale horizontally with the cluster module or multiple containers behind a load balancer. Unhandled promise rejections and a blocked loop are the two failure modes to watch.",
 f:"Ask how they would find a blocked event loop in production — event loop lag metrics, not guesswork."},

{k:"design", s:"support", l:"any", id:"d9",
 q:"Applications you support are built as microservices behind an API gateway. What does the gateway do, and why does that shape matter when you are triaging an incident?",
 a:"The gateway is the single entry point: it routes to the right service, terminates TLS, authenticates, applies rate limits and often aggregates responses. For triage it matters because a user-visible failure can be at the gateway, at one service, or at a dependency behind it — so you narrow by layer, checking gateway logs and status codes first, then the specific service, then its database or downstream. It also means one slow service can look like a site-wide outage if the gateway or a caller has no timeout, and that a correlation ID threaded through the hops is what makes a request traceable at all.",
 f:"Good answers reach for correlation IDs and per-layer narrowing. Weak answers describe restarting things."},

/* ---------------------------------------------------- integration patterns */
{k:"integration", s:"all", l:"any", id:"i1",
 q:"Two services must stay in step. Walk me through choosing between a synchronous API call, a message queue, and a shared database.",
 a:"A synchronous call is simplest and gives an immediate answer, but couples availability — if the callee is down the caller fails — so it suits a read the caller cannot proceed without. A queue decouples availability and smooths spikes, at the cost of eventual consistency and at-least-once delivery the consumer must handle idempotently; it suits work that can complete later. A shared database is the one to avoid: it couples the two through a schema nobody owns, so neither can change independently and a bad query in one takes down the other.",
 f:"Ask them to defend the shared database honestly — it is sometimes the pragmatic choice for a short migration window, but they should name the cost."},

{k:"integration", s:"all", l:"any", id:"i2",
 q:"What does idempotency mean for an API, and how would you make a payment endpoint idempotent?",
 a:"An idempotent operation produces the same result whether it is applied once or many times, which matters because networks make clients retry without knowing whether the first attempt landed. For payments the usual approach is a client-supplied idempotency key sent with the request; the server stores the key with the result of the first attempt and, on seeing it again, returns the stored result instead of charging again. The key needs a retention window, and the store-and-check must be atomic or two concurrent retries both pass the check.",
 f:"Ask what happens when two retries arrive at the same instant. The answer should involve a unique constraint or a lock, not ‘check then insert’."},

{k:"integration", s:"all", l:"senior", id:"i3",
 q:"How do you version a public API without breaking existing consumers?",
 a:"Prefer additive, backward-compatible change — new optional fields, new endpoints — so most consumers never need to move. When a breaking change is unavoidable, version explicitly (URI path or a media-type header), run both versions side by side, publish a deprecation window with dates, and instrument usage so you know who is still on the old one before you switch it off. Tolerant readers on the consumer side — ignore unknown fields, do not depend on field order — reduce how often you are forced to version at all.",
 f:"Look for measuring actual consumer usage before retiring a version. Anyone who says ‘we just announce it’ has not run a real deprecation."},

{k:"integration", s:"all", l:"any", id:"i4",
 q:"A downstream partner API is slow and occasionally times out. How do you stop that becoming your outage?",
 a:"Set an explicit, short timeout on every outbound call — the default of ‘none’ is what kills services — and bound the work with a circuit breaker so you fail fast while they are unhealthy. Isolate the calls with a bulkhead, a separate connection pool or thread pool, so their slowness cannot consume all your capacity. Retry only idempotent calls, with backoff and jitter and a cap. Then decide the degraded behaviour: serve cached or partial data, or queue the work and reconcile later, rather than propagating their failure to your user.",
 f:"Timeouts and bulkheads are the tell. A candidate who only says ‘retry’ is making the problem worse."},

{k:"integration", s:"all", l:"any", id:"i5",
 q:"Compare REST and messaging for integration. When is each the wrong choice?",
 a:"REST is right for synchronous, request-scoped reads and commands where the caller needs the outcome now and the contract is resource-shaped; it is the wrong choice for long-running work, for fan-out to many consumers, and where the callee's availability must not affect the caller. Messaging is right for asynchronous work, fan-out, load levelling and durability across outages; it is the wrong choice when the caller genuinely needs an answer to continue, or when the team has no appetite for the operational weight of a broker, dead-letter handling and poison-message replay.",
 f:"Ask what they do with a poison message. Dead-letter queues and a replay path separate theory from experience."},

{k:"integration", s:"dotnet", l:"any", id:"i6",
 q:"Azure Service Bus queues versus topics — when do you use each, and what do sessions and dead-lettering give you?",
 a:"A queue is point-to-point: one message, one consumer, competing consumers for throughput. A topic is publish/subscribe: each subscription gets its own copy, with filters deciding which messages it sees, so you add consumers without touching the producer. Sessions give FIFO ordering and state for a related group of messages — all events for one order — at the cost of throughput, since a session is handled by one consumer at a time. Dead-lettering moves messages that repeatedly fail or expire to a side queue so they stop blocking the main flow and can be inspected and replayed.",
 f:"Ask how they would replay a dead-lettered message safely. Idempotency should come up again here."},

{k:"integration", s:"java", l:"any", id:"i7",
 q:"In Kafka, how do partitions, consumer groups and offsets work together, and where does ordering actually hold?",
 a:"A topic is split into partitions; ordering is guaranteed only within a partition, not across the topic, and the partition is chosen by the message key — so all events for one entity must share a key to stay ordered. A consumer group divides partitions among its members, one partition to one consumer at a time, so group parallelism is capped by partition count. Offsets record how far a group has read; committing after processing gives at-least-once delivery, committing before gives at-most-once, and exactly-once needs transactions or an idempotent consumer.",
 f:"Ask what happens to ordering if they add partitions later, or rebalance mid-batch. Both are real production traps."},

{k:"integration", s:"node", l:"any", id:"i8",
 q:"How would you design a webhook receiver that a third party calls, so it is reliable and not abusable?",
 a:"Verify authenticity first — an HMAC signature over the raw body with a shared secret, plus a timestamp to reject replays — then respond 2xx quickly and do the real work asynchronously, because providers time out and retry. Treat delivery as at-least-once and deduplicate on the provider's event ID, since the same event will arrive twice. Bound the risk: validate payload size and shape, rate limit per sender, and dead-letter events you cannot process so a single bad payload does not stall the pipeline.",
 f:"Verifying the signature over the raw, unparsed body is the detail most people miss. Ask about replay protection too."},

{k:"integration", s:"support", l:"any", id:"i9",
 q:"A nightly batch feed from an upstream system did not arrive and the downstream reports are wrong. Walk me through how you work that, and what the design should have had in place.",
 a:"Confirm the failure first: check the scheduler for the job state, the landing directory or queue for the file, and the upstream's own run status, so you know whether it failed, ran late, or never started. Establish blast radius — which reports and which business process — and communicate that with an ETA before fixing. Then either chase the upstream or reprocess once the file lands, validating record counts and checksums rather than assuming. By design it should have had a file-arrival SLA with alerting on absence, not just on failure, dependency-aware scheduling so downstream jobs do not run on stale data, and an idempotent reprocess path so a rerun cannot double-load.",
 f:"Alerting on a file that never arrives — as opposed to a job that errored — is the discriminating point. Also ask how a rerun avoids duplicates."},

/* ---------------------------------------------------- security considerations */
{k:"security", s:"all", l:"any", id:"s1",
 q:"Explain the difference between authentication and authorisation, and where each belongs in a microservices setup.",
 a:"Authentication establishes who the caller is; authorisation decides what that identity may do. Authentication is best done once at the edge \u2014 the gateway or an identity provider \u2014 issuing a signed token the services can validate without a round trip. Authorisation cannot live only at the edge, because only the service owning a resource knows whether this user may touch this record; the gateway can do coarse checks, the service must do the fine-grained one. Services validate the token's signature, issuer, audience and expiry locally rather than calling the identity provider per request.",
 f:"Ask where they would enforce \u2018user A may only see their own orders\u2019. If the answer is \u2018at the gateway\u2019, that is the gap."},

{k:"security", s:"all", l:"any", id:"s2",
 q:"What is OAuth 2.0 actually for, and how does an access token differ from an ID token?",
 a:"OAuth 2.0 is a delegated authorisation framework: it lets an application act on a resource owner's behalf without holding their password. An access token is for the API \u2014 it carries scopes saying what the bearer may do and the API validates it. An ID token is OpenID Connect, not OAuth proper: it is a statement to the client about who authenticated and when, and should never be sent to an API as a credential. Access tokens should be short-lived with refresh tokens held server-side; for browser apps the authorisation code flow with PKCE is the current guidance, not implicit.",
 f:"Conflating the two tokens is common. Ask which one they would send in an Authorization header, and why implicit flow fell out of favour."},

{k:"security", s:"all", l:"any", id:"s3",
 q:"How do you keep secrets \u2014 connection strings, API keys \u2014 out of trouble across environments?",
 a:"They never live in source control or config files in the repo. They sit in a managed secret store \u2014 Key Vault, Secrets Manager, or the platform's own \u2014 and are read at startup or on demand by an identity the workload already has, so there is no bootstrap secret to protect. Prefer managed identity or workload identity over a stored credential entirely. Beyond storage: scope each secret to least privilege, rotate on a schedule and after any suspected exposure, keep them out of logs and exception messages, and scan the repository and CI history so an old committed key is actually found.",
 f:"Managed identity \u2014 removing the credential rather than hiding it \u2014 is the senior answer. Ask what they do the day a key leaks."},

{k:"security", s:"all", l:"senior", id:"s4",
 q:"Name the injection and access-control risks you design against, and how you prevent them.",
 a:"SQL injection is prevented by parameterised queries or an ORM, never string concatenation, with stored procedures no protection if they concatenate internally. Cross-site scripting is prevented by contextual output encoding and a content security policy, not input blacklists. Broken access control \u2014 the most common real-world failure \u2014 means every request re-checks authorisation server-side against the authenticated identity, never trusting an ID in the URL or a role claim from the client. Add CSRF protection for cookie-based sessions, validate and bound all input, and avoid mass assignment by binding to an explicit DTO rather than the domain entity.",
 f:"Insecure direct object reference is the one to probe: \u2018what stops me changing the id in the URL to someone else's?\u2019"},

{k:"security", s:"all", l:"any", id:"s5",
 q:"What does defence in depth mean, and what would you put between the internet and a database?",
 a:"No single control is trusted to hold, so independent layers each reduce risk and a breach of one does not expose everything. From the edge inward: WAF and DDoS protection, TLS termination, an authenticating gateway with rate limits, then application-layer authorisation, then network segmentation so the database is not routable from the internet at all, private endpoints and firewall rules, a least-privilege database account rather than a superuser, encryption at rest and in transit, and audit logging. Each layer assumes the one outside it has already failed.",
 f:"Look for network segmentation and least-privilege database accounts, not just \u2018we use HTTPS and a firewall\u2019."},

{k:"security", s:"dotnet", l:"any", id:"s6",
 q:"How does Microsoft Entra ID fit into securing an ASP.NET Core API, and what is managed identity doing for you?",
 a:"Entra ID issues OAuth 2.0 / OIDC tokens; the API validates the JWT's signature against Entra's published keys and checks issuer, audience, expiry and the scopes or app roles it requires \u2014 configured through the JWT bearer middleware, with authorisation policies rather than scattered role checks. Managed identity removes the credential problem for service-to-service and resource access: Azure gives the app an identity in the directory, the platform supplies tokens at runtime, and nothing has to store a client secret. RBAC on the target resource then decides what that identity may do.",
 f:"Ask the difference between system-assigned and user-assigned managed identity, and when a user-assigned one is worth it."},

{k:"security", s:"java", l:"any", id:"s7",
 q:"How would you secure a Spring Boot service, and what does the filter chain give you?",
 a:"Spring Security inserts a chain of servlet filters ahead of the application: authentication filters establish the principal, then authorisation decisions are made against the request. For an API you disable form login and session-based CSRF, configure it stateless, and validate a JWT as a resource server, mapping claims to authorities. Method-level annotations then enforce fine-grained rules close to the logic. Beyond that: keep dependencies patched \u2014 Log4Shell and Spring4Shell are the reminder \u2014 run with a non-root user, and never expose actuator endpoints publicly without securing them.",
 f:"Ask why CSRF protection is usually disabled for a stateless API but essential for a cookie-based one."},

{k:"security", s:"node", l:"any", id:"s8",
 q:"What are the main security risks specific to a Node and npm application, and how do you manage them?",
 a:"The dependency tree is the big one: a small application pulls in hundreds of transitive packages, so you pin versions with a lockfile, audit continuously, watch for typosquatting and unmaintained packages, and keep CI failing on known critical advisories. Beyond that: never build shell commands from user input, prototype pollution through unsafe deep-merge of request bodies, regular expressions that backtrack catastrophically and block the single thread, and JWTs verified with an explicit algorithm rather than trusting the header. Run the process as non-root and keep secrets out of environment dumps and error responses.",
 f:"Prototype pollution and ReDoS are the ones that separate a Node specialist from a generalist."},

{k:"security", s:"support", l:"any", id:"s9",
 q:"You are supporting a banking platform. What are your obligations around production data, and how does maker-checker protect the bank?",
 a:"Production access is least-privilege and audited: you use a named account, read-only where possible, elevate through an approved change for anything that writes, and never extract customer data to a local machine or a ticket attachment. PII and card data are masked in logs and lower environments. Maker-checker separates duties so the person requesting a customer-impacting change is not the person approving it \u2014 it protects against both error and fraud, and the audit trail of who raised and who approved is itself the control. Any direct data fix goes through change management with a rollback and a record of rows touched.",
 f:"Ask what they would do if asked to run an UPDATE on production to fix a customer's balance quickly. The right answer involves refusing the shortcut."},

/* ---------------------------------------------------- scalability */
{k:"scale", s:"all", l:"any", id:"c1",
 q:"Vertical versus horizontal scaling \u2014 and what has to be true of your application before horizontal works?",
 a:"Vertical means a bigger machine: simple, no code change, but bounded by the largest instance and a single point of failure. Horizontal means more instances behind a load balancer: effectively unbounded and more resilient, but it demands the application be stateless \u2014 no in-memory session, no local file writes, no in-process cache assumed to be shared, no singleton scheduler that must run once. State moves to a distributed cache, a database or object storage; scheduled work needs a leader election or a distributed lock so it runs once across the fleet.",
 f:"The scheduler running on every instance is a classic. Ask what happens to their background job when they scale to three pods."},

{k:"scale", s:"all", l:"any", id:"c2",
 q:"Where would you introduce caching, and how do you handle invalidation?",
 a:"Closest to the consumer first \u2014 CDN for static assets, HTTP caching headers, then a distributed cache such as Redis for expensive shared reads, then the database's own buffer. Pick the strategy deliberately: cache-aside is the default, read-through and write-through when you want the cache authoritative. Invalidation is the hard half: a short TTL bounds staleness cheaply, event-based invalidation is precise but needs the write path to publish, and versioned keys avoid the update-and-delete race entirely. Guard against stampede with a lock or staggered expiry so a popular key expiring does not send every request to the database at once.",
 f:"Cache stampede and the thundering herd are the mark of production experience. Ask what happens when a hot key expires under load."},

{k:"scale", s:"all", l:"any", id:"c3",
 q:"A read-heavy API is slowing down under growth. Walk me through diagnosing and fixing it, in order.",
 a:"Measure first: find whether latency is in the application, the database or a downstream, using traces and percentiles rather than averages \u2014 the p99 is what users feel. Usually it is the database, so look at the slow query log and execution plans for missing or unused indexes, N+1 patterns from the ORM, and queries selecting far more than needed. Fix the query and the index before adding infrastructure. Then cache the expensive, stable reads; then add read replicas and route reads to them, accepting replication lag; then consider denormalised projections. Adding servers ahead of fixing a missing index just multiplies the cost of the same bad query.",
 f:"Order matters. A candidate who starts with \u2018add more instances\u2019 or \u2018move to NoSQL\u2019 is guessing."},

{k:"scale", s:"all", l:"senior", id:"c4",
 q:"Explain database sharding and the problems it creates.",
 a:"Sharding partitions rows across independent databases by a shard key, so each holds a subset and writes scale beyond one machine. The shard key decides everything: a poor one creates hot shards, and a key you cannot query by forces scatter-gather across every shard. Cross-shard joins and transactions effectively stop being available, so the data model must keep related data in one shard. Rebalancing as you grow is the real pain \u2014 consistent hashing or a lookup table of ranges makes it tractable. Because of all that, it is a last resort after read replicas, caching and query tuning.",
 f:"Ask them to pick a shard key for a multi-tenant SaaS and defend it against a single very large tenant."},

{k:"scale", s:"all", l:"any", id:"c5",
 q:"What is backpressure, and how do you apply it?",
 a:"Backpressure is the system telling an upstream producer to slow down rather than silently accumulating work it cannot finish \u2014 without it, queues grow, memory fills and latency climbs until something falls over. In practice it is bounded queues that reject or block when full, rate limiting and quotas at the edge, concurrency limits on worker pools, a 429 with Retry-After so clients back off, and load shedding that drops low-priority work to protect the critical path. The principle is that failing fast and visibly beats degrading slowly and invisibly.",
 f:"Look for bounded queues. An unbounded in-memory queue is the anti-pattern to name."},

{k:"scale", s:"dotnet", l:"any", id:"c6",
 q:"How does async/await in .NET help throughput, and when does it not?",
 a:"For I/O-bound work, await releases the thread back to the pool while the operation is outstanding, so a fixed number of threads serves far more concurrent requests \u2014 that is a throughput win, not a latency win for the individual call. It does nothing for CPU-bound work, where it only adds overhead. The traps are blocking on async code with .Result or .Wait(), which can deadlock and certainly wastes threads; async void outside event handlers, which loses exceptions; and forgetting ConfigureAwait(false) in library code on a framework with a synchronisation context.",
 f:"Ask them to explain thread pool starvation. That is where sync-over-async actually bites."},

{k:"scale", s:"java", l:"any", id:"c7",
 q:"How do you tune a JVM service for throughput, and what do you look at when it slows down?",
 a:"Start with evidence, not flags: heap usage and GC pause time and frequency from GC logs, thread states from a thread dump, and allocation rate from a profiler. Most \u2018GC problems\u2019 are really allocation problems or a leak \u2014 a growing old generation across full GCs means retention, not tuning. Set heap explicitly and match the collector to the goal, G1 for balanced pause and throughput. Beyond the JVM, connection pool size is a frequent bottleneck: too small and threads queue, too large and the database is overwhelmed. Thread dumps during a stall usually show the real answer.",
 f:"Ask what a heap that keeps growing after full GC tells them. Also listen for connection pool sizing \u2014 commonly missed."},

{k:"scale", s:"node", l:"any", id:"c8",
 q:"How do you scale a Node service, and how do you find what is limiting it?",
 a:"One process uses one core, so the first step is one process per core via cluster or, better, multiple containers behind a load balancer, which also gives you rolling deploys. Keep processes stateless so any instance can serve any request, with session and cache in Redis. To find the limit, measure event loop lag first \u2014 if it climbs, something is blocking the loop and no amount of horizontal scale fixes the per-request latency. Then look at outbound connection pools and keep-alive, at synchronous work hidden in libraries, and at memory growth from retained closures or unbounded caches.",
 f:"Event loop lag as the primary signal is the answer worth hearing."},

{k:"scale", s:"support", l:"any", id:"c9",
 q:"An overnight batch is finishing later each week and now threatens the SLA. How do you approach it?",
 a:"Trend it first: get the run durations over weeks and find whether the whole job or one step is growing, because the fix differs. Usually it is data volume against a query whose plan has tipped, or a dependency that now starts later. Check the execution plan and indexes for the heavy step, look for growth in the driving tables, and confirm whether the window itself shrank because an upstream feed moved. Short term, protect the SLA by re-sequencing or splitting the job; longer term the fixes are partitioning or archiving the growing table, parallelising independent steps, or moving to incremental rather than full processing. Then add alerting on run duration trending, not just on failure.",
 f:"Alerting on a job that is merely getting slower \u2014 before it breaches \u2014 is what separates proactive from reactive support."},

/* ---------------------------------------------------- multi-tenancy */
{k:"tenancy", s:"all", l:"any", id:"t1",
 q:"Describe the models for multi-tenant data isolation and the trade-offs between them.",
 a:"Three broadly. Database per tenant gives the strongest isolation, simple per-tenant backup and restore, and easy noisy-neighbour control, but cost and operational effort grow with tenant count and schema migrations must run everywhere. Schema per tenant within one database is a middle ground with moderate isolation and fewer instances. Shared schema with a tenant ID column on every row is cheapest and scales to many small tenants, but isolation is entirely enforced by code, so one missing WHERE clause is a cross-tenant data leak. Many products mix them \u2014 shared for small tenants, dedicated for large or regulated ones.",
 f:"Ask which they would choose for a regulated banking client with a data-residency requirement, and why."},

{k:"tenancy", s:"all", l:"senior", id:"t2",
 q:"In a shared-schema design, how do you make sure one tenant can never read another's data?",
 a:"Never rely on developers remembering a filter. The tenant identity comes from the authenticated token, never from a request parameter the client can change. Then enforce it below the query: a global query filter in the ORM, or row-level security in the database keyed to a session variable set from the token, so an unfiltered query returns nothing rather than everything. Add a repository layer that cannot construct a tenant-less query, tests that assert cross-tenant reads fail, and a database account without the privilege to bypass RLS. Defence in depth, because the failure mode is a breach, not a bug.",
 f:"\u2018We always add a WHERE clause\u2019 is the wrong answer. Look for enforcement the developer cannot forget."},

{k:"tenancy", s:"all", l:"any", id:"t3",
 q:"How do you stop one tenant degrading service for everyone \u2014 the noisy neighbour problem?",
 a:"Measure per tenant first, so you can attribute load rather than guess. Then apply quotas and rate limits per tenant at the gateway, not just globally, and enforce concurrency caps so one tenant's burst cannot occupy every worker. Isolate expensive work \u2014 reports, bulk imports \u2014 onto separate queues or worker pools with their own limits, so an eight-hour export does not starve interactive traffic. For tenants who genuinely need more, the answer is a dedicated tier or shard rather than letting them consume the shared pool.",
 f:"Per-tenant metrics are the prerequisite. Ask how they would even know which tenant caused yesterday's slowdown."},

{k:"tenancy", s:"all", l:"any", id:"t4",
 q:"How do you handle per-tenant configuration and customisation without forking the product?",
 a:"Keep it as data, not code. A tenant configuration store holds feature flags, limits, branding and workflow options, resolved at runtime with sensible defaults so a new tenant needs no entries. Where behaviour genuinely differs, use a strategy or plugin interface with the implementation selected by configuration, rather than conditionals scattered through the codebase. Version the configuration schema and validate it, and keep a hard rule that no tenant gets a code branch \u2014 the moment one does, every future release has to be tested twice.",
 f:"Ask what they do when a large client demands behaviour no configuration flag supports. Listen for how they resist the fork."},

{k:"tenancy", s:"all", l:"senior", id:"t5",
 q:"How do schema migrations and per-tenant onboarding work when you have hundreds of tenants?",
 a:"Migrations must be automated, versioned and idempotent, applied by a tool such as Flyway or EF migrations rather than by hand, and they must be backward compatible so old and new application versions can both run against the schema during a rolling deploy \u2014 expand first, migrate data, contract later. With a database per tenant you need an orchestrated run across all of them with per-tenant status tracking, retry for failures, and the ability to resume; you cannot have tenant 300 fail and leave the estate half-migrated. Onboarding should be a single automated path that provisions storage, seeds reference data and registers the tenant, so adding a tenant is not a project.",
 f:"Expand-and-contract is the phrase to listen for. Ask how they deploy a column rename with zero downtime."},

{k:"tenancy", s:"dotnet", l:"any", id:"t6",
 q:"How would you implement tenant resolution and isolation in an ASP.NET Core application?",
 a:"Resolve the tenant early, in middleware, from the authenticated token's tenant claim \u2014 or from host name or route for pre-auth flows \u2014 and put it in a scoped service so everything downstream in that request can see it without passing it around. Then enforce it in the data layer: EF Core global query filters applied to every tenant-scoped entity so a forgotten WHERE cannot leak, and the tenant set on insert automatically via SaveChanges rather than by the caller. Keep caches tenant-keyed so one tenant cannot be served another's cached response, and make sure background jobs establish tenant context explicitly since there is no request to derive it from.",
 f:"Background jobs and cache keys are where tenant context usually leaks. Ask about both."},

{k:"tenancy", s:"java", l:"any", id:"t7",
 q:"How would you implement multi-tenancy in a Spring Boot and JPA application?",
 a:"Resolve the tenant in a filter or interceptor from the JWT claim and hold it in a ThreadLocal context, being careful to clear it and to propagate it explicitly across async boundaries and thread pools, where a ThreadLocal will not follow. For separate databases, a routing DataSource selects the connection per tenant; for shared schema, Hibernate filters or a tenant-aware base entity apply the predicate centrally, or row-level security enforces it in the database. Connection pooling needs thought with database-per-tenant, since a pool per tenant multiplies connections quickly.",
 f:"The ThreadLocal not surviving an @Async call or a CompletableFuture is the trap. Ask how they handle it."},

{k:"tenancy", s:"support", l:"any", id:"t8",
 q:"You support a platform serving several client organisations from shared infrastructure. What does that change about how you handle an incident?",
 a:"Scope first: establish whether the problem is one tenant or all of them, because that changes both the diagnosis and who you tell \u2014 a single-tenant issue is usually data or configuration, an all-tenant issue is usually shared infrastructure. Communications must be tenant-scoped so you do not tell every client about another's outage, and nothing you share can leak one client's data into another's ticket. When you query production to investigate, filter by that tenant and use read-only access, since a broad query can both expose and lock across tenants. And check whether one tenant's volume caused it, because noisy neighbours show up as a shared-infrastructure incident.",
 f:"Look for the instinct to scope by tenant before diagnosing, and for care about cross-tenant disclosure in comms."},

/* ---------------------------------------------------- infrastructure */
{k:"infra", s:"all", l:"any", id:"n1",
 q:"What does a good CI/CD pipeline do, and what belongs in CI as opposed to CD?",
 a:"CI runs on every commit and protects the main branch: build, unit and integration tests, static analysis, dependency and secret scanning, and producing one immutable versioned artifact. CD takes that same artifact and promotes it through environments with configuration injected per environment \u2014 never rebuilding per environment, because then you deployed something you did not test. Deployment should be repeatable and reversible: automated, with a health check gate, and a rollback that is a tested path rather than a hope. Anything slow or flaky belongs outside the commit gate, or it trains people to ignore red builds.",
 f:"\u2018Build once, promote the same artifact\u2019 is the line to listen for. Ask how they roll back a bad release."},

{k:"infra", s:"all", l:"any", id:"n2",
 q:"Explain blue-green and canary deployments, and when a rolling update is enough.",
 a:"Blue-green runs two complete environments and switches traffic at once: rollback is instant, but you pay for double capacity and must handle database compatibility across both. Canary sends a small slice of traffic to the new version, watches error rate and latency, and widens gradually \u2014 the best risk control, but it needs good per-version metrics and automated rollback to be worth the complexity. A rolling update replaces instances gradually and is sufficient for most internal services where a brief mixed-version window is acceptable. All three require backward-compatible database changes, because two versions run at once in every case.",
 f:"The database compatibility point is the one most candidates miss. Press on it."},

{k:"infra", s:"all", l:"any", id:"n3",
 q:"What is infrastructure as code and why does it matter beyond convenience?",
 a:"Infrastructure is declared in version-controlled files \u2014 Terraform, Bicep, ARM \u2014 and applied by a tool rather than configured by hand in a portal. It matters because it makes environments reproducible and identical, so \u2018works in staging\u2019 means something; it makes changes reviewable and auditable through pull requests; it makes disaster recovery a rerun rather than an archaeology exercise; and it eliminates configuration drift, which is the usual cause of an environment-specific bug. State management and drift detection are the operational disciplines that come with it, along with keeping secrets out of the templates.",
 f:"Ask what they do when someone changes a resource in the portal by hand. Drift detection and re-apply is the answer."},

{k:"infra", s:"all", l:"any", id:"n4",
 q:"What would you monitor on a production service, and what is the difference between monitoring and observability?",
 a:"Monitoring answers questions you thought of in advance \u2014 the known dashboards and thresholds. Observability is being able to answer questions you did not anticipate, from the telemetry you already emit: structured logs with a correlation ID, metrics, and distributed traces tying a request across services. For a request-serving service the core signals are traffic, error rate, latency at percentiles, and saturation of the resources that bind it. Alert on symptoms users feel \u2014 error rate, latency, queue depth \u2014 rather than on causes like CPU, and make every alert actionable or it will be ignored.",
 f:"Alerting on symptoms rather than CPU is the mature answer. Ask what they would do about an alert that fires every night and nobody acts on."},

{k:"infra", s:"all", l:"senior", id:"n5",
 q:"Containers and orchestration \u2014 what does Kubernetes actually give you over running containers directly?",
 a:"A container gives a reproducible, isolated runtime; that alone does not run a service. Orchestration adds scheduling across nodes, self-healing by restarting failed containers and rescheduling off dead nodes, horizontal autoscaling, service discovery and load balancing, rolling deployments with health gates, configuration and secret injection, and declarative desired state that the control plane reconciles. The cost is real operational complexity \u2014 networking, storage, RBAC, resource requests and limits \u2014 so for a handful of services a managed app platform is often the better trade.",
 f:"Ask when they would not use Kubernetes. A candidate who thinks it is always right has not paid for it."},

{k:"infra", s:"all", l:"any", id:"n6",
 q:"What do RPO and RTO mean, and how do they drive a disaster recovery design?",
 a:"RPO is how much data you can afford to lose, measured in time; RTO is how long you can afford to be down. They are business decisions that dictate the architecture and the cost. A low RPO needs synchronous replication or frequent log shipping; a low RTO needs a warm or hot standby rather than restoring from backup. Active-passive with a documented failover is cheaper than active-active, which gives near-zero RTO but demands the application tolerate multi-region writes. The part people skip is testing: an untested failover plan is an assumption, so DR drills and verified backup restores are what make the numbers real.",
 f:"Ask when they last tested a restore. Backups nobody has restored are the classic finding."},

{k:"infra", s:"dotnet", l:"any", id:"n7",
 q:"Azure App Service, Azure Functions and AKS \u2014 how do you choose?",
 a:"App Service for a conventional long-running web application or API: managed platform, easy deployment slots and scaling, least operational overhead. Functions for event-driven, bursty or scheduled work billed per execution \u2014 good for glue and background processing, with cold start and execution duration as the constraints, and the isolated worker model for current .NET. AKS when you need fine control over networking, sidecars, mixed workloads or a portable Kubernetes footprint, accepting that you now own cluster operations. Choose the least infrastructure that meets the requirement, and let load pattern and operational appetite decide rather than fashion.",
 f:"Ask how they would handle a Function with a cold start problem on a user-facing path."},

{k:"infra", s:"java", l:"any", id:"n8",
 q:"What do you configure when containerising a Spring Boot service, and what goes wrong if you do not?",
 a:"Set resource requests and limits, and make sure the JVM respects the container limit rather than the host's memory \u2014 modern JVMs are container-aware, but an explicit max heap leaving headroom for metaspace and native memory avoids the OOM kill that looks like a crash with no stack trace. Expose liveness and readiness probes from actuator, distinguishing them properly: readiness gates traffic during startup and warm-up, liveness restarts a wedged process, and conflating them causes restart loops under load. Externalise configuration, run as non-root, and use a layered or multi-stage image so rebuilds are small.",
 f:"The liveness-versus-readiness distinction is the one that bites in production. Probe it."},

{k:"infra", s:"support", l:"any", id:"n9",
 q:"What does a disaster recovery failover exercise actually test, and what have you seen go wrong in one?",
 a:"It tests whether the documented plan works with the people and systems you actually have: that the standby is current within RPO, that the switch itself works, that dependencies \u2014 DNS, certificates, downstream integrations, batch schedules \u2014 follow the switch rather than still pointing at the primary, and that the team can execute under time pressure. The common failures are stale runbooks, credentials or certificates that expired on the standby, a dependency nobody mapped, data that replicated but was not validated, and no rehearsed decision about who declares the failover. The fallback path matters as much as the failover.",
 f:"Ask who makes the call to fail over, and how they verify data integrity afterwards rather than just that the site responds."},

/* ---------------------------------------------------- architecture */
{k:"arch", s:"all", l:"any", id:"a1",
 q:"Monolith or microservices \u2014 how do you decide, and what does microservices cost?",
 a:"A well-structured monolith is the right default: one deployment, in-process calls, easy transactions and refactoring. Microservices buy independent deployment, independent scaling and team autonomy, and they are worth it when teams are blocked on each other's release cycles or when parts of the system have genuinely different scaling or availability needs. The cost is real: network calls that fail, distributed transactions replaced by sagas and eventual consistency, distributed tracing to debug anything, versioned contracts, and much heavier operations. Splitting a domain you do not yet understand produces a distributed monolith \u2014 all the cost, none of the independence.",
 f:"The distributed monolith is the phrase worth hearing. Ask how they would decide where the service boundaries go."},

{k:"arch", s:"all", l:"senior", id:"a2",
 q:"How do you decide where a service boundary belongs?",
 a:"By business capability and the data it owns, not by technical layer \u2014 a service per bounded context, with one clear owner of each piece of data, rather than a \u2018data service\u2019 and a \u2018logic service\u2019. The test is cohesion and coupling: if a typical change touches three services, the boundary is wrong; if two services must always deploy together, they are one service. Watch for chatty call patterns and for a shared database, which both mean the split is artificial. Rate of change and team ownership matter too \u2014 parts that change together and are owned by the same people belong together.",
 f:"\u2018If a change touches three services, the boundary is wrong\u2019 is the insight. Ask for an example from their own work."},

{k:"arch", s:"all", l:"any", id:"a3",
 q:"Explain layered, hexagonal and clean architecture. What is the common idea?",
 a:"All three keep business logic independent of delivery and infrastructure concerns. Layered stacks presentation over application over domain over data, with dependencies pointing down \u2014 simple but the domain often ends up depending on the data layer. Hexagonal, or ports and adapters, puts the domain at the centre with ports defining what it needs and adapters implementing them for HTTP, database, or a broker, so the domain has no outward dependency. Clean architecture is the same idea with named rings and an explicit dependency rule: source dependencies point inward only, and crossing outward is done through interfaces defined inside. The payoff is testability and the freedom to change infrastructure; the cost is indirection that is not worth it for a small service.",
 f:"Ask where they would put a call to a third-party API, and where the interface for it is declared. Inward-pointing dependencies is the test."},

{k:"arch", s:"all", l:"any", id:"a4",
 q:"What are the SOLID principles, and which one do you see violated most?",
 a:"Single responsibility \u2014 one reason to change; open/closed \u2014 extend without modifying; Liskov substitution \u2014 a subtype must honour the base type's contract; interface segregation \u2014 many small interfaces beat one wide one; dependency inversion \u2014 depend on abstractions, and let the high-level policy define the interface the low-level detail implements. In practice single responsibility is violated most, producing service classes that do everything, though the more damaging one is dependency inversion misunderstood as \u2018use a DI container\u2019 \u2014 injecting a concrete dependency through a container still leaves the policy depending on the detail.",
 f:"The DI-container misunderstanding is a good discriminator. Ask who should own the interface, the caller or the implementer."},

{k:"arch", s:"all", l:"senior", id:"a5",
 q:"How do you document and justify a significant architectural decision?",
 a:"An architecture decision record: the context and forces, the options considered, the decision, and the consequences including what it makes harder \u2014 kept in the repository beside the code and never edited after acceptance, only superseded. The value is that six months later the team can see why, and can tell a deliberate trade-off from an accident. Justification should be against the quality attributes that matter to this system \u2014 latency, availability, cost, time to market, compliance \u2014 stated as concretely as possible, and it should name what was given up. A decision with no downside listed usually means the alternatives were not seriously considered.",
 f:"\u2018What did you give up?\u2019 is the follow-up. An architect who cannot answer it was not really choosing."},

{k:"arch", s:"all", l:"senior", id:"a6",
 q:"How would you approach modernising a large legacy application that cannot be stopped?",
 a:"Incrementally, with the strangler fig pattern: put a facade in front of the legacy system and route slices of functionality to new implementations one at a time, so the old system shrinks rather than being replaced in a big bang. Sequence by value and risk \u2014 start where change is frequent or pain is highest, not with the easiest module. Data is the hard part: decide the owner of each entity, and run a synchronisation or dual-write with reconciliation for as long as both systems live, knowing that period is where the bugs are. Keep the old path working and reversible until the new one has proved itself in production.",
 f:"Ask how they keep two data stores consistent during the transition, and how they decide the first slice."},

{k:"arch", s:"all", l:"any", id:"a7",
 q:"What non-functional requirements do you insist on establishing before designing, and why do they matter more than the feature list?",
 a:"Expected load and its shape, latency targets at percentiles, availability target and what downtime costs, data volume and growth, retention and residency rules, security and compliance obligations, and the recovery objectives. They matter more because they determine the architecture where features mostly determine the code \u2014 a system for a thousand users and one for ten million differ structurally, and retrofitting an availability or residency requirement usually means rebuilding. They also need to be numbers rather than adjectives: \u2018fast\u2019 and \u2018highly available\u2019 cannot be designed against or tested.",
 f:"Look for insisting on numbers. Ask what they do when the business cannot give a figure \u2014 a good answer proposes one and gets it challenged."},

{k:"arch", s:"node", l:"any", id:"a8",
 q:"What is a micro frontend and what does Module Federation solve?",
 a:"A micro frontend splits a browser application into independently developed and deployed pieces, usually aligned to teams or domains, so one team can ship without a coordinated release. Module Federation lets one build consume modules from another at runtime rather than at build time, so a shell can load a remote's code without bundling it, with shared dependencies negotiated so React is not loaded five times. The costs are real: version skew between remotes, a heavier initial load if sharing is misconfigured, harder end-to-end debugging, and the need for a shared design system or the product looks assembled from parts.",
 f:"Ask how they keep a shared dependency such as React from being loaded multiple times, and what happens when a remote is down."},

{k:"arch", s:"support", l:"any", id:"a9",
 q:"Describe the architecture of an application you support, from the user's request to the database, and where you have seen it fail.",
 a:"A strong answer traces the whole path \u2014 client, load balancer, web tier, application tier, the service that owns the logic, its cache, its database, and any downstream integrations \u2014 and names the technologies at each hop. Then it identifies real failure points from experience: a connection pool exhausted, a certificate expiry, a dependency timing out, a batch holding locks, a disk or tablespace filling. What distinguishes a good support engineer is knowing which layer a given symptom points to and what evidence would confirm it, rather than reciting a diagram.",
 f:"Push for specifics: which component, what symptom, how they proved it. Generic answers here mean they have watched dashboards rather than diagnosed."}

];
