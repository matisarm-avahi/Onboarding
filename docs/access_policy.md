Repository Governance & Access Model

Roles and access. Access is based on least privilege. Admins (the owner and one backup) manage settings, secrets, and branch protection. Maintainers merge approved pull requests and manage releases. Contributors (Write) push feature branches and open PRs. Everyone else gets Read or Triage. Roles are assigned through GitHub Teams so access is easy to audit and revoke.

Branch protection on main. No direct pushes. Every change needs a pull request with at least one approving review, and CI checks (build, tests, lint) must pass before merging. Stale approvals are dismissed on new commits, conversations must be resolved, force pushes and deletions are disabled, and the rules apply to admins too.

Branch rules:

Restrict creations
Only allow users with bypass permission to create matching refs.

Restrict updates
Only allow users with bypass permission to update matching refs.

Restrict deletions
Only allow users with bypass permissions to delete matching refs.

Require linear history
Prevent merge commits from being pushed to matching refs.

Require signed commits
Commits pushed to matching refs must have verified signatures.

Require a pull request before merging
Require all commits be made to a non-target branch and submitted via a pull request before they can be merged.
Required approvals
The number of approving reviews that are required before a pull request can be merged.

Dismiss stale pull request approvals when new commits are pushed
New, reviewable commits pushed will dismiss previous pull request review approvals

Require review from Code Owners
Require an approving review in pull requests that modify files that have a designated code owner.

Require conversation resolution before merging
All conversations on code must be resolved before a pull request can be merged.

Require an additional approval for unattributed Copilot pull requests
When Copilot opens a pull request without a human collaborator, require one more approving review if a non-zero approval count is required.
Allowed merge methods
When merging pull requests, you can allow any combination of merge commits, squashing, or rebasing. At least one option must be enabled.

Block force pushes
Prevent users with push access from force pushing to refs.

Secrets. Credentials are never committed. A repository secret (TEST_SECRET) is stored under Settings → Secrets and variables → Actions and used in workflows as ${{ secrets.TEST_SECRET }}. Only Admins can create or rotate secrets, and they are masked in logs. 


Together, these controls ensure every change is reviewed and tested, and that only trusted people can change settings or access credentials.