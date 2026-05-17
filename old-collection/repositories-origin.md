As per request of my master advisor, we will have to replace our first collection step, which would be to search github for the repos that we would actually clone in the next collection step.

We are going to use https://seart-ghs.si.usi.ch/ instead, here is their Github repository: https://github.com/seart-group/ghs. This application has already scraped Github for us, they have a database that can be queried and results exported to csv and json files.

The motivation to do so is for reproducibility, we will have a fixed, perfectly known, list of repositories documented. Instead of randomly asking Github search API to return some repos. For my academic paper based on this project, this is essential, if not, mandatory.

The folder github-seach/ already contains the results of the search I did at https://seart-ghs.si.usi.ch/,
We have results for Python, Java, JS and TS. In both formars, csv and json. For each search the same set of filter were used, the ones we defined at collection/config.py, 100 commits at least, 500 stars at least , skipping forks, sorting by descending order of stars.

now here what we are going to do:

1- Remove the collection step code and test for scraping Github, this will reduce our overall LOC count.
Now we will rely solely on the presence of the folder github-search with appropriate content to set the repos in the sqlite database. So instead of first step being Github direct collection, it will be processing of the github-search/ content. the sqlite must be created accordingly to the content of the github-search/ folder. We also need unit tests for this.
2- We need to review and alter our extraction process. Previously we had filters for not collecting repositories that would match certain criterias, toy projects, student projects, etc, there is already a keyword list for that. we MUST keep filtering those low quality projects on the first step of collection (processing of github-search) so we do not over clone repositories that are not meaningful.
3- We need to review that the second collection step, cloning the repos is compatible with what we altered in step one and perform any changes that might be needed. Looks like it wont change much since the cloning step will rely on the sqlite file just as before and if we did a good job at refactoring the first collection process, it will stay the same for cloning.
4 - overall review of the documentation, it is important remove the old github manual search form the docs, replace it with information about https://seart-ghs.si.usi.ch/ including why we are using it, where the output should be located (as the user will have to do the scraping in the website manually), the expected file names (follow the existing pattern language-results.file-extension).
5- Do a review of unit tests, see if there is anything to be updated.
6- Finish with your onw review of the codebase after these changes, see what we might have left behing and what else is worth updating/documenting