import os
import pandas as pd
import numpy as np
import re
import yaml
from yaml.loader import SafeLoader
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import f1_score
from base_functions import load_data, analyze_result, show_result, save_result

model = SentenceTransformer('all-mpnet-base-v2')
THRESHOLD = 0.7
BATCH_SIZE = 1000

linking_statement = [r"(?i)fixes:?", r"(?i)what's changed:?", r"(?i)other changes:?", r"(?i)documentation:?",
                     r"(?i)features:?", r"(?i)new contributors:?", r"(?i)bug fixes:?", r"(?i)changelog:?",
                     r"(?i)notes:?", r"(?i)improvements:?", r"(?i)deprecations:?", r"(?i)minor updates:?",
                     r"(?i)changes:?", r"(?i)fixed:?", r"(?i)maintenance:?", r"(?i)added:?"]

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


if __name__ == '__main__':
    repos = []
    data_path = os.path.join(ROOT_DIR, 'data')
    for subdir, dirs, files in os.walk(data_path):
        repos.extend(dirs)
    
    test_cases_path = os.path.join(ROOT_DIR, 'test_cases.yaml')
    test_cases = None
    with open(test_cases_path, 'r') as f:
        test_cases = yaml.load(f, Loader=SafeLoader)

    def approach2(test_name, train_repos, test_repos, _type):
        file_name = 'labeled_commits.csv' if _type == 'origin' else 'labeled_commits_abstract.csv'
        # load changelog sentences database
        all_changelog_sentences = []

        for repo in train_repos:
            path = os.path.join(data_path, repo, 'release_notes.csv')
            df = pd.read_csv(path)
            for release_note in df['Release Note']:
                changelog_sentences = str(release_note).split('\n')
                all_changelog_sentences.extend(changelog_sentences)

        # Remove duplicate sentences and linking statements
        all_changelog_sentences = list(set(all_changelog_sentences))
        all_changelog_sentences = [sentence for sentence in all_changelog_sentences  
                                        if not (any(re.match(pattern, sentence) for pattern in linking_statement) or sentence == '')]
        
        X_test = []
        y_test = []
        # Load commit messages and expected label of commits
        for repo in test_repos:
            path = os.path.join(data_path, repo, file_name)
            commit, label = load_data(path)
            X_test = np.concatenate((X_test, commit), axis=0)
            y_test = np.concatenate((y_test, label), axis=0)

        # Encode all changelog sentences
        print('Start to encode changelog sentences')
        # Load encoded changelog sentences
        # encoded_file = os.path.join(ROOT_DIR, 'models', 'encoded_vectors', f'{test_name}_{_type}.npy')
        # with open(encoded_file, 'rb') as f:
        #     encoded_changelog_sentences = np.load(f)

        # Encode and save encoded changelog sentences
        encoded_changelog_sentences = model.encode(all_changelog_sentences)
        print('Successfully encoded changelog sentences')
        print('Encoded changelog sentences shape:', encoded_changelog_sentences.shape)
        encoded_file = os.path.join(ROOT_DIR, 'models', 'encoded_vectors', f'{test_name}_{_type}.npy')
        with open(encoded_file, 'wb') as f:
            np.save(f, encoded_changelog_sentences)

        # Encode test commit
        print('Start to encode test commit')
        encoded_test_commit = model.encode(X_test)
        print('Successfully encoded test commit')
        print('Encoded test commit shape:', encoded_test_commit.shape)

        # print('Start to calculate cosine similarity')
        scores = np.asarray([])
        # Split commit into some batchs (can't work with whole commits because of numpy max allocate memory capacity)
        rounds = len(encoded_test_commit) // BATCH_SIZE
        for i in range(rounds):
            cosine_similarities = cosine_similarity(encoded_test_commit[i * BATCH_SIZE: (i + 1) * BATCH_SIZE], encoded_changelog_sentences)
            scores = np.concatenate((scores, np.amax(cosine_similarities, axis=1)), axis=0)
        # Calculate rest commits
        cosine_similarities = cosine_similarity(encoded_test_commit[rounds * BATCH_SIZE:], encoded_changelog_sentences)
        
        
        scores = np.concatenate((scores, np.amax(cosine_similarities, axis=1)), axis=0)
        # Save scores of each test so that no need to wait a long time to see result next time
        score_file = os.path.join(ROOT_DIR, 'models', 'approach2_scores', f'{test_name}_{_type}.npy')
        with open(score_file, 'wb') as f:
            np.save(f, scores)
        
        # Load scores from previous running session
        # score_file = os.path.join(ROOT_DIR, 'models', 'approach2_scores', f'{test_name}_{_type}.npy')
        # with open(score_file, 'rb') as f:
        #     scores = np.load(f)
        y_preds = np.where(scores >= THRESHOLD, 1, 0)
        print('Successfully calculated cosine similarity')
        # Score result
        path = os.path.join(ROOT_DIR, 'sample_wrong_cases', 'encode_cosine.yaml')
        result = analyze_result(path, (test_name, _type), X_test, y_preds, y_test)
        show_result(result)
        result_path = os.path.join(ROOT_DIR, 'encode_cosine.yaml')
        save_result(result_path, (test_name, _type), result)

    for test_case, test_repos in test_cases.items():
        train_repos = list(set(repos) - set(test_repos))
        approach2(test_name=test_case, train_repos=train_repos, test_repos=test_repos, _type='abstract')
        
