import logging
from collections import Counter
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from indra.belief import check_extra_evidence, get_stmt_evidence
from indra.statements import get_all_descendants, Statement, Evidence


logger = logging.getLogger(__name__)


class SklearnBase(object):
    """Base class to wrap an Sklearn model with statement preprocessing.

    Parameters
    ----------
    model : sklearn or similar model
        Any instance of a classifier object supporting the methods `fit`
        and `predict_proba`.

    """
    def __init__(self, model):
        self.model = model

    @staticmethod
    def get_all_sources(stmts):
        """Get a list of all the source_apis supporting the given statements.

        Parameters
        ----------
        stmts : list of INDRA Statements
            A list of INDRA Statements to collect source APIs for.

        Returns
        -------
        list of str
            A list of (unique) source_apis found in the set of statements.
        """
        return list(set([ev.source_api for s in stmts for ev in s.evidence]))

    def stmts_to_matrix(self, stmts, *args, **kwargs):
        raise NotImplementedError('Need to implement the stmts_to_matrix '
                                   'method')

    def df_to_matrix(self, df, *args, **kwargs):
        raise NotImplementedError('Need to implement the df_to_matrix '
                                   'method')

    def to_matrix(self,
        stmt_data: Union[np.ndarray, List[Statement], pd.DataFrame]
        extra_evidence: Optional[List[List[Evidence]] = None
    ) -> np.ndarray:
        """Gets stmt data matrix by calling appropriate method in subclass.

        If `stmt_data` is already a matrix, it is returned directly; if
        a DataFrame of Statement metadata, `self.df_to_matrix` is called;
        if a list of Statements, `self.stmts_to_matrix` is called.

        Parameters
        ----------
        stmt_data : numpy.ndarray, pandas.DataFrame, or list[Statement]
            Statement content to be used to generate a feature matrix.

        Returns
        -------
        numpy.ndarray
            Feature matrix for the statement data.
        """
        # If we got a Numpy array, just use it!
        if isinstance(stmt_data, np.ndarray):
            stmt_arr = stmt_data
        # Otherwise check if we have a dataframe or a list of statements
        # and call the appropriate *_to_matrix method
        elif isinstance(stmt_data, pd.DataFrame):
            if extra_evidence is not None:
                raise ValueError('extra_evidence cannot be used with a '
                                 'statement DataFrame.')
            stmt_arr = self.df_to_matrix(stmt_data)
        # Check if stmt_data is a list (i.e., of Statements):
        elif isinstance(stmt_data, list)
            stmt_arr = self.stmts_to_matrix(stmt_data, extra_evidence)
        # If it's something else, error
        else:
            raise TypeError('stmt_data must be a numpy array, DataFrame, or '
                            'list of Statements')
        return stmt_arr

    def fit(self, stmt_data, y_arr, *args, **kwargs):
        """Preprocess the stmt data and pass to sklearn model fit method.

        Additional `args` and `kwargs` are passed to the `fit` method of the
        wrapped sklearn model.

        Parameters
        ----------
        stmt_data : numpy.ndarray, pandas.DataFrame, or list[Statement]
            Statement content to be used to generate a feature matrix.
        y_arr : numpy.ndarray
        """
        # Check dimensions of stmts (x) and y_arr
        if len(stmt_data) != len(y_arr):
            raise ValueError("Number of stmts/rows must match length of y_arr.")
        # Get the data matrix based on the stmt list or stmt DataFrame
        stmt_arr = self.to_matrix(stmt_data)
        # Call the fit method of the internal sklearn model
        self.model.fit(stmt_arr, y_arr, *args, **kwargs)
        return self

    def predict_proba(self, stmt_data, extra_evidence=None):
        # Call the prediction method of the internal sklearn model
        stmt_arr = self.to_matrix(stmt_data, extra_evidence)
        return self.model.predict_proba(stmt_arr)

    def predict(self, stmt_data, extra_evidence=None):
        stmt_arr = self.to_matrix(stmt_data, extra_evidence)
        return self.model.predict(stmt_arr)

    def predict_log_proba(self, stmt_data, extra_evidence=None):
        stmt_arr = self.to_matrix(stmt_data, extra_evidence)
        return self.model.predict_log_proba(stmt_arr)


class CountsModel(SklearnBase):
    """Predictor based on source evidence counts and other stmt properties.

    Parameters
    ----------
    source_list : list of str
        List of strings denoting the evidence sources (evidence.source_api
        values) used for prediction.
    use_stmt_type : bool
        Whether to include statement type as a feature.
    use_num_members : bool
        Whether have a feature denoting the number of members of the statement.
        Primarily for stratifying belief predictions about Complex statements
        with more than two members.

    If using a dataframe, it should have columns corresponding to those
    generated by the IndraNets:

    agA_ns
    agA_id
    agA_name
    agB_ns
    agB_id
    agB_name
    stmt_type
    stmt_hash
    source_counts

    Alternatively, if the DataFrame doesn't have a source_counts column,
    it should have columns with names matching the sources in source list.
    """
    def __init__(self, model, source_list, use_stmt_type=False,
                 use_num_members=False, use_num_pmids=False):
        # Call superclass constructor to store the model
        super(CountsModel, self).__init__(model)
        self.use_stmt_type = use_stmt_type
        self.use_num_members = use_num_members
        self.source_list = source_list
        self.use_num_pmids = use_num_pmids
        # Build dictionary mapping INDRA Statement types to integers
        if use_stmt_type:
            all_stmt_types = get_all_descendants(Statement)
            self.stmt_type_map = {t.__name__: ix
                                  for ix, t in enumerate(all_stmt_types)}

    def stmts_to_matrix(self, stmts, extra_evidence=None):
        # Check our list of extra evidences
        check_extra_evidence(extra_evidence, len(stmts))

        # Add categorical features and collect source_apis
        cat_features = []
        stmt_sources = set()
        for ix, stmt in enumerate(stmts):
            stmt_ev = get_stmt_evidence(stmt, ix, extra_evidence)
            # Collect all source_apis from stmt evidences
            pmids = set()
            for ev in stmt_ev:
                stmt_sources.add(ev.source_api)
                pmids.add(ev.pmid)
            # Collect non-source count features (e.g. type) from stmts
            feature_row = []
            # One-hot encoding of stmt type
            if self.use_stmt_type:
                stmt_type_ix = self.stmt_type_map[type(stmt).__name__]
                type_features = [1 if ix == stmt_type_ix else 0
                                 for ix in range(len(self.stmt_type_map))]
                feature_row.extend(type_features)
            # Add field for number of members
            if self.use_num_members:
                feature_row.append(len(stmt.agent_list()))
            # Add field with number of unique PMIDs
            if self.use_num_pmids:
                feature_row.append(len(pmids))
            # Only add a feature row if we're using some of the features.
            if feature_row:
                cat_features.append(feature_row)

        # Before proceeding, check whether all source_apis are in
        # source_list
        if stmt_sources.difference(set(self.source_list)):
            logger.info("source_list does not include all source_apis "
                             "in the statement data.")

        # Get source count features
        num_cols = len(self.source_list)
        num_rows = len(stmts)
        x_arr = np.zeros((num_rows, num_cols))
        for stmt_ix, stmt in enumerate(stmts):
            stmt_ev = get_stmt_evidence(stmt, ix, extra_evidence)
            sources = [ev.source_api for ev in stmt_ev]
            src_ctr = Counter(sources)
            for src_ix, src in enumerate(self.source_list):
                x_arr[stmt_ix, src_ix] = src_ctr.get(src, 0)

        # If we have any categorical features, turn them into an array and
        # add them to matrix
        if cat_features:
            cat_arr = np.array(cat_features)
            x_arr = np.hstack((x_arr, cat_arr))
        return x_arr


    def df_to_matrix(self, df):
        required_cols = {'agA_id', 'agA_name', 'agA_ns', 'agB_id', 'agB_name',
                         'agB_ns', 'stmt_hash', 'stmt_type'}
        # Currently, statement DataFrames are not expected to contain
        # number of members or num_pmids as a data column, hence we raise a
        # ValueError if either of these are set
        if self.use_num_members:
            raise ValueError('use_num_members not supported for statement '
                             'DataFrames.')
        if self.use_num_pmids:
            raise ValueError('use_num_pmids not supported for statement '
                             'DataFrames.')
        # Make sure that the dataframe contains at least all of the above
        # columns
        if not required_cols.issubset(set(df.columns)):
            raise ValueError('Statement DataFrame is missing required '
                             'columns.')
        # Check for the source_counts column. If it's there, we're good
        if 'source_counts' in df.columns:
            has_sc_col = True
        # If it's not, make sure that we have columns named for sources in
        # self.source_list:
        else:
            has_sc_col = False
            for source in self.source_list:
                if source not in df.columns:
                    raise ValueError(f'Expected column "{source}" not in the '
                                      'given statement DataFrame')

        # Add categorical features and collect source_apis
        cat_features = []
        stmt_sources = set()
        # For every statement entry in the dataframe...
        for rowtup in df.itertuples():
            # Collect statement sources
            # ...if there's a source_counts col with dicts
            if has_sc_col:
                stmt_sources |= set(rowtup.source_counts.keys())
            # Collect non-source count features (e.g. type) from stmts
            feature_row = []
            # One-hot encoding of stmt type
            if self.use_stmt_type:
                stmt_type_ix = self.stmt_type_map[rowtup.stmt_type]
                type_features = [1 if ix == stmt_type_ix else 0
                                 for ix in range(len(self.stmt_type_map))]
                feature_row.extend(type_features)
            # Only add a feature row if we're using some of the features.
            if feature_row:
                cat_features.append(feature_row)

        # Before proceeding, check whether all source_apis are in
        # source_list. If we don't have a source_counts dict, we don't look
        # for columns beyond the sources in the source list, and we are
        # guaranteed to have all of them because of the check performed above
        source_diff = stmt_sources.difference(set(self.source_list))
        if has_sc_col and source_diff:
            logger.warning("source_list does not include all source_apis "
                           f"in the statement data: {str(source_diff)}")

        # Get source count features
        num_cols = len(self.source_list)
        num_rows = len(df)
        x_arr = np.zeros((num_rows, num_cols))
        for stmt_ix, rowtup in enumerate(df.itertuples()):
            for src_ix, src in enumerate(self.source_list):
                # Get counts from the source_count dictionary
                if has_sc_col:
                    x_arr[stmt_ix, src_ix] = rowtup.source_counts.get(src, 0)
                # ...or get counts from named source column
                else:
                    x_arr[stmt_ix, src_ix] = rowtup._asdict()[src]

        # If we have any categorical features, turn them into an array and
        # add them to matrix
        if cat_features:
            cat_arr = np.array(cat_features)
            x_arr = np.hstack((x_arr, cat_arr))
        return x_arr


class EvidenceModel(SklearnBase):
    def __init__(self, model):
        # Call superclass constructor to store the model
        super(EvidenceModel, self).__init__(model)
        # Build dictionary mapping INDRA Statement types to integers
        all_stmt_types = get_all_descendants(Statement)
        self.stmt_type_map = {t.__name__: ix
                              for ix, t in enumerate(all_stmt_types)}

    def stmts_to_matrix(self, stmts):
        # Categorical features to be one-hot encoded
        cat_features = []
        # Numerical features
        char_distance = []
        sentence_length = []
        for stmt in stmts:
            feature_row = []
            if len(stmt.evidence) != 1:
                raise ValueError('EvidenceModel requires a list of '
                                 'statements with only a single evidence as '
                                 'input')
            # Collect all source_apis from stmt evidences
            ev = stmt.evidence[0]
            stmt_type_ix = self.stmt_type_map[type(stmt).__name__]
            type_features = [1 if ix == stmt_type_ix else 0
                             for ix in range(len(self.stmt_type_map))]
            feature_row.extend(type_features)
            sentence_length.append(len(ev.text))
            cat_features.append(feature_row)

        # If we have any categorical features, turn them into an array and
        # add them to matrix
        cat_arr = np.array(cat_features)
        return cat_arr


