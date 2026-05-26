# Release Review Skill

Use this skill when preparing, reviewing, or documenting a Variant Pathogenicity
Rater release. The release review should confirm functionality, safety,
documentation, provenance, and roadmap alignment. It is not a clinical
validation statement.

## Release Checklist

1. Combiner diff review: confirm whether the classification combiner changed.
   If it changed, review every rule change and require candidate-leakage tests.
2. Pytest pass: run the full test suite for the release branch.
3. Benchmark pass: run the curated SNV/small-indel benchmark suite.
4. Smoke pass: run the real-data smoke suite.
5. Candidate evidence leakage check: verify candidate/review-note evidence does
   not affect final classification.
6. Applied evidence separation check: verify applied evidence and candidate
   evidence remain separately represented in structured output and reports.
7. Report wording safety check: verify reports do not imply clinical sign-out,
   automatic evidence acceptance, or overconfidence for VUS.
8. CLI/MCP consistency: verify CLI, MCP, Python, batch, and annotated-batch
   workflows preserve the same safety semantics.
9. Docs update check: verify user-facing and developer-facing docs match the
   current behavior.
10. Provenance preservation: verify provider, annotation, literature,
    population, computational, and generated evidence include source and
    limitation context.
11. Review-required preservation: verify classification results, applied
    evidence, reports, batch records, and failed records retain human-review
    requirements.
12. Limitations update: verify `docs/KNOWN_LIMITATIONS.md` reflects current
    unsupported scope and safety boundaries.
13. Release notes update: record scope, added behavior, safety posture, test
    results, non-blocking issues, and release status.

## Alpha Readiness

Alpha readiness means the feature surface is coherent enough for internal
developer testing. Core flows should run, schemas should be stable enough for
iteration, major unsupported scope should be documented, and safety boundaries
must already be explicit.

Alpha does not require broad benchmark coverage or real-world validation, but it
does require that candidate-only evidence not affect classification and that
human-review-required language be visible.

Minimum alpha expectations:

- Relevant unit/integration tests pass.
- Combiner behavior is reviewed.
- Unsupported scope is documented.
- Provider failures become limitations or structured errors.
- No online dependency is required by default.

## Beta Readiness

Beta readiness means the system is suitable for controlled internal workflow
testing. Single, batch, annotated-batch, CLI, MCP, reporting, normalization,
annotation adapters, provenance, context consistency, and noisy-input handling
should be stable enough for realistic offline testing.

Minimum beta expectations:

- Full pytest pass.
- Benchmark pass.
- Real-data smoke pass.
- No blocking candidate evidence leakage.
- Reports clearly separate applied and candidate evidence.
- Online features remain opt-in.
- Known limitations and release notes are current.
- Human review is required everywhere.

Beta remains non-clinical. It is not a sign-out release and should not be
described as clinically validated.

## Release Readiness

Release readiness means the project has satisfied the full release checklist for
the intended scope and has documented residual risks. For this project, release
readiness still means release as a review-support tool unless a separate
validated clinical governance process exists.

Minimum release expectations:

- Full pytest, benchmark, and smoke suites pass on the release branch.
- Combiner diff review is complete and documented.
- Candidate leakage and applied/candidate separation checks pass.
- Report wording has been reviewed for safety.
- CLI/MCP/batch behavior is consistent.
- Provenance and limitations are preserved.
- Release notes, known limitations, roadmap, and project state are updated.
- Residual non-blocking risks are listed explicitly.

Do not mark a release as clinically validated unless a separate clinical
validation program, qualified review, and regulatory/sign-out process has been
completed and documented outside this software release checklist.
