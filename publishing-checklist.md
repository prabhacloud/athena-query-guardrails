# Publishing checklist

## Content and confidentiality

- [x] Article uses generic professional knowledge only.
- [x] No client, employer, account, bucket, database, table, or person is named.
- [x] Example identifiers are obviously synthetic.
- [x] No unverified biographical or profile claims are included.
- [x] AWS claims are linked to official AWS documentation.
- [x] Perform a final human read for voice and preferred spelling.

## Demonstration

- [x] The default command is read-only and credential-free.
- [x] Unit and template tests pass locally.
- [x] CloudFormation has no hard-coded account or region identifiers.
- [x] The results bucket is encrypted and blocks public access.
- [x] Cleanup behavior and retained bucket caveat are documented.
- [x] Deploy to a temporary AWS account after reviewing the change
      set and expected costs.
- [x] Capture sanitized evidence and delete the stack afterward.
- [x] Delete all versions from the retained S3 bucket and delete the bucket.

## AWS Builder Center

- [x] Title, subtitle, excerpt-friendly opening, tags, and image are prepared.
- [x] Article is marked `Published`.
- [x] Upload the 1200 x 675 PNG cover image.
- [x] Preview formatting, code blocks, links, and image alt text.
- [x] Save as a Builder Center draft.
- [x] Request action-time confirmation before publishing.
- [x] Publish the Builder Center article.

## GitHub

- [x] README, source, tests, sample SQL, and infrastructure are prepared.
- [x] Create the public repository.
- [ ] Select and add the intended open-source license.
- [x] Add the final repository URL to the article.
- [x] Review the Git history for secrets and unintended files.
- [x] Request action-time confirmation before making the repository public or
      pushing the final release.
- [x] Push the tested source, examples, infrastructure, and tests.

## LinkedIn

- [x] Companion LinkedIn sharing is recorded as mandatory after publication.
- [x] Prepare the final LinkedIn post after the Builder Center URL is known.
- [x] Request action-time confirmation before publishing the LinkedIn post.
- [x] Publish the companion LinkedIn post with article and GitHub links.

