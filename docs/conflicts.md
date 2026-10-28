
Step-by-Step Instructions to Trigger a Conflict

1. Create and initialize a repository with a base file:bash
git init
echo "Hello World" > file.txt
git add file.txt
git commit -m "Initial commit"
2. Create and switch to a new branch, then modify the file:bash
git checkout -b feature-branch
echo "Hello from feature branch" > file.txt
git add file.txt
git commit -m "Change in feature branch"
3. Switch back to the main branch and make a conflicting edit to the same line:bash
git checkout main
echo "Hello from main branch" > file.txt
git add file.txt
git commit -m "Change in main branch"
4. Attempt to merge the feature branch into main:bash
git merge feature-branch

What Happens Next

• Git will stop the merge process and output a message saying AUTOMATIC MERGE FAILED or CONFLICT (content): Merge conflict in file.txt.
• If you open file.txt, you will see Git's conflict markers (<<<<<<< HEAD, =======, and >>>>>>> feature-branch) showing both competing versions side-by-side.
• The conflict is solved line by line (in case of multiple changes) deciding for each one which line stays.