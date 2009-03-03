"""

Clustering and consensus clustering classes


Copyright 2008 Michael Seiler
Rutgers University
miseiler@gmail.com

This file is part of ConsensusCluster.

ConsensusCluster is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

ConsensusCluster is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with ConsensusCluster.  If not, see <http://www.gnu.org/licenses/>.


"""

import math, numpy, sys, random
import distance, treetype, display

from mpi_compat import *


class BaseCluster(object):
    """

    BaseCluster

        Common variables and methods to each clustering method

        Properties

            distance        - distance function
            datapoints      - sdata.samples
            num_clusters    - K value
            distance_matrix - Distance matrix (Optional in all cases)
            num_samples     - Number of samples
            vec_len         - Length of each sample data vector
            data_matrix     - "Current" sample data.  May be subsampled, etc
                              Treat sdata.samples[x].data as the "True" data,
                              which should not be used in any algorithm.

    """

    def __init__(self, datapoints, data_matrix, num_clusters, distance_metric, distance_matrix=None):

        self.__dict__ = { 'distance': distance_metric, 'datapoints': datapoints, 'num_clusters': num_clusters, 
                          'distance_matrix': distance_matrix, 'num_samples': len(datapoints), 
                          'vec_len': len(data_matrix[0]), 'data_matrix': data_matrix }
        
    def _gen_distance_matrix(self, data_matrix, distance, num_samples):
        """Generate a distance matrix so that we can use indices to specify distance rather than data vectors"""

        distance_matrix = numpy.zeros((num_samples, num_samples), dtype = float)

        for i in xrange(num_samples):
            for j in xrange(1, num_samples - i):
                k, m = i, i+j

                distance_matrix[k][m] = distance(data_matrix[k], data_matrix[m])

        return distance_matrix + distance_matrix.transpose()


class HierarchicalCluster(BaseCluster):
    """

    HierarchicalCluster

        Performs hierarchical clustering.

        NOTE: This function uses a hash function to memoize distances between every two cluster combination!
        This reduces running time significantly but can be VERY memory-intensive.

        Usage:

            HierarchicalCluster(datapoints, data_matrix, num_clusters, distance_metric, linkage='average', distance_matrix)

                datapoints      - sdata.samples
                data_matrix     - Current sample data
                num_clusters    - K
                distance_metric - Distance function
                linkage         - The linkage
                                    Can be one of the following:
                                        'average'   - The average of the distances between each element of two clusters
                                        'single'    - The smallest distance between one element of one cluster and one element of the other
                                        'complete'  - The largest distance between an element of one cluster and an element of the other

                                        or a function taking a single parameter corresponding to a list of distances between all the elements
                                        of one cluster and all the elements of another.

                distance_matrix - A distance matrix

        Properties:

                tree            - Recursive tree datatype, suitable for producing a dendrogram.  See treetype
                                  The tree leaves will have value equal to the sample index

        This class, when initialised, performs the clustering procedure.  The result is each sample in datapoints has its cluster_id property
        set to a number.  All of the samples with that particular cluster_id have been clustered together.

    """

    def __init__(self, datapoints, data_matrix, num_clusters, distance_metric, linkage='average', distance_matrix=None, **kwds):

        BaseCluster.__init__(self, datapoints, data_matrix, num_clusters, distance_metric, distance_matrix)

        if linkage == 'average':
            linkage = numpy.ndarray.mean
        elif linkage == 'single':
            linkage = numpy.ndarray.min
        elif linkage == 'complete':
            linkage = numpy.ndarray.max

        #At the moment, each independent leaf represents a cluster
        self.tree = [ treetype.Tree(value = x) for x in xrange(self.num_samples) ]

        if distance_matrix is None:
            distance_matrix = self._gen_distance_matrix(data_matrix, distance_metric, self.num_samples)

        self._cluster_data(distance_matrix, linkage)

        #Shed the list
        self.tree = self.tree[0]

    def _cluster_data(self, distance_matrix, linkage):
        """
        Run until no more clusters are present. Useful for dendrogram.
        When K has been reached, assign clusters.

        """

        #Locals are faster
        tree, num_clusters = self.tree, self.num_clusters

        cache = {} #Cache of distances between sets of clusters
        maxint = sys.maxint
    
        while len(tree) > 1:
            if len(tree) == num_clusters:
                self._assign_clusters()

            clust_len = len(tree)
            best = [maxint]
            
            for i in xrange(clust_len):
                for j in xrange(1, clust_len - i):

                    k, m = i, i+j

                    fst_clust, snd_clust = tuple(tree[k].sequence), tuple(tree[m].sequence)
                    key = (fst_clust, snd_clust)
    
                    if key not in cache:
                        dist = linkage(distance_matrix.take(fst_clust, 0).take(snd_clust, 1))
                        cache[key] = dist
                    else:
                        dist = cache[key]
    
                    if dist < best[0]:
                        best = [dist, k, m]

            tree.append(treetype.Tree(left=tree[best[1]], right=tree[best[2]], dist=best[0])) #Make a stack

            del tree[best[2]]
            del tree[best[1]]
    
    def _assign_clusters(self):
        """Assign cluster ids to each obj"""

        def assign_node_clust(node, id):
            if node.value is not None:
                node.cluster_id = id
                return
            else:
                assign_node_clust(node.left, id)
                assign_node_clust(node.right, id)

                node.cluster_id = id

        for i in xrange(len(self.tree)):
            assign_node_clust(self.tree[i], i)
            
            for index in self.tree[i].sequence:
                self.datapoints[index].cluster_id = i


class KMeansCluster(BaseCluster):
    """

    KMeansCluster

        Performs K-Means Clustering

        Usage:
            
            KMeansCluster(datapoints, num_clusters, distance_metric)

                datapoints      - sdata.samples
                data_matrix     - Current sample data
                num_clusters    - K
                distance_metric - Distance function

        This class, when initialised, performs the clustering procedure.  The result is each sample in datapoints has its cluster_id property
        set to a number.  All of the samples with that particular cluster_id have been clustered together.

    """

    def __init__(self, datapoints, data_matrix, num_clusters, distance_metric, **kwds):

        BaseCluster.__init__(self, datapoints, data_matrix, num_clusters, distance_metric)
        
        centroids = self._gen_initial_centroids(data_matrix)

        self._cluster_data(datapoints, centroids, distance_metric, data_matrix)

    def _cluster_data(self, datapoints, centroids, distance, data_matrix):
        """Run until the centroids have not been moved"""
        
        num_samples  = self.num_samples
        num_clusters = self.num_clusters
        vec_len      = self.vec_len
        average      = numpy.average
        
        moved_flag = 1

        while moved_flag:
            moved_flag = 0
            cluster_ids = dict() # key: centroid number, value: list of indices

            #Assign clusters
            for i in xrange(num_samples):
                cluster_ids.setdefault(min([ (distance(centroids[j], data_matrix[i]), j) for j in xrange(num_clusters) ])[1], []).append(i)

            #Move centroids
            for i in xrange(num_clusters):
                if cluster_ids.has_key(i):
                    cluster_data_matrix = data_matrix.take(tuple(cluster_ids[i]), 0)

                    for j in xrange(vec_len):
                        val = cluster_data_matrix[:,j].mean()

                        if not centroids[i][j] == val:
                            centroids[i][j] = val
                            moved_flag = 1

        #Assign cluster ids to datapoints
        for cluster_id in cluster_ids:
            for idx in cluster_ids[cluster_id]:
                datapoints[idx].cluster_id = cluster_id

    def _gen_initial_centroids(self, data_matrix):
        """Generate initial cluster centroids"""

        ran = random.random

        mins = data_matrix.min(0) #Column min
        maxs = data_matrix.max(0) #Column max

        return numpy.array([ [ ran() * (maxs[i] - mins[i]) + mins[i] for i in xrange(self.vec_len) ] for j in xrange(self.num_clusters) ], dtype=float)


class PAMCluster(BaseCluster):
    """

    PAMCluster

        Performs Partition Around Medoids clustering procedure

        Usage:

            PAMCluster(datapoints, data_matrix, num_clusters, distance_metric, distance_matrix)

                datapoints      - sdata.samples
                data_matrix     - Current sample data
                num_clusters    - K
                distance_metric - Distance function
                distance_matrix - Optional distance matrix

        This class, when initialised, performs the clustering procedure.  The result is each sample in datapoints has its cluster_id property
        set to a number.  All of the samples with that particular cluster_id have been clustered together.

    """

    def __init__(self, datapoints, data_matrix, num_clusters, distance_metric, distance_matrix=None, **kwds):

        BaseCluster.__init__(self, datapoints, data_matrix, num_clusters, distance_metric, distance_matrix)

        num_samples = self.num_samples

        if distance_matrix is None:
            distance_matrix = self._gen_distance_matrix(data_matrix, distance_metric, num_samples)

        #Work
        medoids = self._cluster_data(random.sample(xrange(num_samples), num_clusters), distance_matrix, num_samples)
        
        #Assign cluster ids
        for j in xrange(num_samples):
            medoid = min([ (distance_matrix[x][j], x) for x in medoids ])[1]
            datapoints[j].cluster_id = medoid

    def _cluster_data(self, medoids, distance_matrix, num_samples):
        """Swap a medoid within a cluster if it reduces the total cost"""

        swapped  = 1
        old_cost = sum([ min([ distance_matrix[x][j] for x in medoids ]) for j in xrange(num_samples) ])

        while swapped:
            swapped = 0

            for i in xrange(self.num_clusters):
                new_medoids = list(medoids)
                old_medoid = medoids[i]

                #I really hope this is faster
                search_space = range(num_samples)
                not_search = new_medoids
                not_search.sort(reverse=True)

                for idx in not_search:
                    del search_space[idx]
    
                for sample_idx in search_space:
                    new_medoids[i] = sample_idx
                    
                    #Objective function
                    new_cost = sum([ min([ distance_matrix[x][j] for x in new_medoids ]) for j in xrange(num_samples) ])

                    if new_cost < old_cost:
                        swapped = 1
                        old_cost = new_cost
                        medoids = list(new_medoids)

        return medoids


class SOMCluster(BaseCluster):
    """

    SOMCluster

        Performs Self-Organising Map clustering

        Usage:

            SOMCluster(datapoints, data_matrix, num_clusters, distance_metric, distance_matrix)

                datapoints      - sdata.samples
                data_matrix     - Current sample data
                num_clusters    - K
                distance_metric - Distance function
                distance_matrix - Optional distance matrix
                hdim            - Horizontal node dimension, must be > 1
                vdim            - Vertical node dimension, must be > 1
                learn_rate      - The learning rate
                num_epochs      - Number of epochs to train nodes

        This class, when initialised, performs the clustering procedure.  The result is each sample in datapoints has its cluster_id property
        set to a number.  All of the samples with that particular cluster_id have been clustered together.

        Notes:
    
            Rather than do a 1-dim analysis, I've found the small 2-dim (vdim of 2 by default) node array to be most accurate.
            This function simulates K-value by restricting the node array to Kx2 dimensions by default.

        WARNING:

            This method can, and probably will, produce more than K clusters from time to time.  This is intentional, and you shouldn't depend
            on exactly K clusters, anyway.

    """

    def __init__(self, datapoints, data_matrix, num_clusters, distance_metric, distance_matrix=None,
                 hdim = None, vdim = None, learn_rate = 0.001, num_epochs = 2000, **kwds):
            
        BaseCluster.__init__(self, datapoints, data_matrix, num_clusters, distance_metric, distance_matrix)

        if hdim is None:
            hdim = num_clusters

        if vdim is None:
            vdim = 2

        if hdim < 2 or vdim < 2:
            raise ValueError, 'Passed node array dimensions less than 2!'

        nodes = self._gen_initial_nodes(data_matrix, hdim, vdim)
        chessdists = self._memo_chessboard_dists(hdim, vdim)

        nodes = self._train_data(data_matrix, distance_metric, nodes, chessdists, hdim, vdim, learn_rate, num_epochs, (hdim + vdim) / 3.)

        self._assign_clusters(nodes, data_matrix, distance_metric, hdim, vdim)

    def _gen_initial_nodes(self, data_matrix, hdim, vdim):
        """Randomly generate the initial node set"""

        mins = data_matrix.min(0) #Column min
        maxs = data_matrix.max(0) #Column max

        ran = random.random
        vec_len = self.vec_len

        return numpy.array([[[ ran() * (maxs[i] - mins[i]) + mins[i] for i in xrange(vec_len) ] for j in xrange(hdim) ] for k in xrange(vdim) ])

    def _memo_chessboard_dists(self, hdim, vdim):

        M = {} #A dict is several times faster in random 4D access than a numpy array, though it takes more memory

        #FIXME: This is symmetric, and this function does twice the work it needs to
        for i in xrange(vdim):
            for j in xrange(hdim):
                for k in xrange(vdim):
                    for l in xrange(hdim):
                        M[(i,j,k,l)] = max(abs(i - k), abs(j - l))

        return M

    def _train_data(self, data_matrix, distance, nodes, chessdists, hdim, vdim, lr, num_epochs, radius):
        """Use the sample set to train the SOM"""

        t_const = num_epochs / math.log(radius)

        node_adjust = numpy.zeros((vdim, hdim, self.vec_len))
        
        e = math.e
        maxint = sys.maxint

        for t in xrange(1, num_epochs):

            new_radius = radius * e**(-t / t_const)
            new_learn = lr * e**(-lr / t_const)
            r = 2 * t * new_radius * new_radius

            for k in xrange(self.num_samples):

                bmu = [maxint]

                #Rather than a one line min([ listcomp ]) here, the added complexity reduces function calls by quite a bit
                for i in xrange(vdim):
                    for j in xrange(hdim):
                        dist = distance(nodes[i][j], data_matrix[k])

                        if dist < bmu[0]:
                            bmu = [dist, i, j]
                
                try:
                    y = bmu[1]
                except:
                    #FIXME: We need a command line way to lower learn rate, or GUI option
                    raise ValueError, "Distance from nodes to data matrix too large? Try lowering learn rate."

                x = bmu[2]
                rad_int = int(new_radius)
                
                #Again, performance vs code succinctness
                if y > rad_int:
                    min_i = y - rad_int - 1
                else:
                    min_i = 0

                if x > rad_int:
                    min_j = x - rad_int - 1
                else:
                    min_j = 0

                max_i = y + rad_int + 1
                max_j = x + rad_int + 1

                if max_i > vdim:
                    max_i = vdim
                if max_j > hdim:
                    max_j = hdim
            
                for i in xrange(min_i, max_i):
                    for j in xrange(min_j, max_j):
                        dist = chessdists[(y,x,i,j)]

                        inf = e**(-dist**2 / r)

                        #W(t+1) = W(t) + O(t)L(t)(V(t) - W(t))
                        node_adjust[i][j] += inf * new_learn * (data_matrix[k] - nodes[i][j])

            nodes += node_adjust
            node_adjust.fill(0)

        return nodes

    def _assign_clusters(self, nodes, data_matrix, distance, hdim, vdim):
        """Assign clusters to each sample in sdata"""

        clusters = dict()

        matches = [ min([ (distance(nodes[i][j], data_matrix[k]), i, j) for i in xrange(vdim) for j in xrange(hdim) ]) for k in xrange(self.num_samples) ]

        for i in xrange(len(matches)):
            key = (matches[i][1], matches[i][2])
            clusters.setdefault(key, []).append(self.datapoints[i])

        for clust in enumerate(clusters):
            for sample in clusters[clust[1]]:
                sample.cluster_id = clust[0]


class ConsensusCluster(object):
    """

    ConsensusCluster

        Creates a consensus of any number of clustering methods, clusters the result as a distance matrix, and reorders it using simulated annealing

        Usage:
            
            ConsensusCluster(sdata, num_clusters, distance_metric, subsamples, subsample_fraction, norm_var,
                             clustering_algs, linkages, final_alg, console)

            sdata               - parsers.Parse object
            num_clusters        - K value, or the number of clusters for the clustering functions to find for each subsample.
            distance_metric     - Distance function
            subsamples          - The number of subsampling iterations to run.  In each subsample, the genes, samples, or both could
                                  be randomly selected for clustering.  This helps to ensure robust clustering.  More subsamples, more
                                  robust clusters.
            subsample_fraction  - The fraction of genes, samples, or both to take each subsample.  0.8 is a good default.
            clustering_algs     - BaseCluster-Derived class which assigns clusters during initialisation
            linkages            - If HierarchicalCluster is chosen, these linkages will be used.  Ignored otherwise
            final_alg           - Either "PAM", "Hierarchical" or a BaseCluster-derived class which supports distance_matrix.
                                  This algorithm is used to cluster the consensus matrix.
            norm_var            - Boolean variable indicating whether the sample data should be standardised to variance 1 across all samples
                                  at each clustering iteration.
            console             - Optional display.ConsoleDisplay object.  Used primarily by the gtk front end.

        This class, when initialised, performs the consensus clustering procedure.  The result is each sample in datapoints has its cluster_id property
        set to a number.  All of the samples with that particular cluster_id have been clustered together.

        Properties

            tree
                
                This is a treetype.Tree object of the final clustering, if Hierarchical clustering was used.  Its leaves have
                value equal to the sample indices (sdata.samples)

            reorder_indices
                
                This is an array of the indices corresponding to the new order the consensus matrix has taken after reordering, using the original matrix as
                a reference.  This can be useful if you plan to use this information, as frequently the consensus matrix ordering will give you more insight
                into the 'true' K value than actual clustering will.

    """

    def __init__(self, sdata, num_clusters=2, distance_metric=distance.euclidean, subsamples=50, subsample_fraction=None, norm_var=False, 
                 clustering_algs=[KMeansCluster], linkages=['average'], final_alg='Hierarchical', console=None, matrix_thresh=0.0, **kwds):

        dim = len(sdata.samples)
        mat = numpy.zeros((dim, dim), dtype=float)

        self.__dict__ = { 'reset_datapoints': False, 'datapoints': sdata.samples, 'num_clusters': num_clusters, 'distance_metric': distance_metric,
                          'sim_matrix_clustcount': mat.copy(), 'sim_matrix_totalcount': mat.copy(), 'consensus_matrix': mat.copy(), 'tree': None,
                          'norm_var': norm_var, 'clustering_algs': clustering_algs, 'linkages': linkages, 'final_alg': final_alg, 'console': console,
                          'matrix_thresh': matrix_thresh }
                         
        if console is None:
            self.console = display.ConsoleDisplay(log=False)

        progress = self.console.progress

        if subsample_fraction is not None:
            self.gene_fraction = int(len(self.datapoints[0].data) * subsample_fraction) #Number of genes to take in a subsample
            self.sample_fraction = int(len(self.datapoints) * subsample_fraction)       #Number of samples to take in a subsample
        else:
            self.sample_fraction = None #No subsampling will be done

        if MPI_ENABLED:
            local_subsamples = mpi.scatter(range(subsamples))
        else:
            local_subsamples = xrange(subsamples)

        #Actual work
        for i in xrange(1, len(local_subsamples) + 1):
            if not MPI_ENABLED:
                progress('Subsample', i, subsamples)
            else:
                progress('Subsample', i*mpi.size, subsamples)  #Not entirely truthful

            self.run_clustering()

        #Finished clustering, now for MPI compatibility step
        clustcount_matrices = [self.sim_matrix_clustcount]     #Total number of times i, j clustered together
        totalcount_matrices = [self.sim_matrix_totalcount]     #Total number of times i, j seen in the same subsample

        if MPI_ENABLED:
            mpi.barrier()
            clustcount_matrices = mpi.gather(clustcount_matrices)
            totalcount_matrices = mpi.gather(totalcount_matrices)

        self.consensus_matrix = self.gen_consensus_matrix(clustcount_matrices, totalcount_matrices)

        self.hcluster_consensus()

        self.console.write('Reordering the consensus matrix...\n\n')
        self.reorder_consensus()

    def _gen_dataset(self):
        """
        Choose a random data perturbation method and return a useful dataset

        1: No change
        2: Samples subsampled
        3: Genes subsampled
        4: Genes and samples subsampled

        If norm_var is True, data is standardised to variance 1 after sampling

        """

        sample = random.sample
        dataset = list(self.datapoints)

        if self.sample_fraction is None:
            a = 1
        else:
            a = random.choice([1,2,3,4])
        
        if a == 2 or a == 4:
            dataset = sample(dataset, self.sample_fraction)
        else:
            dataset = sample(dataset, len(dataset))

        M = numpy.array([ x.data for x in dataset ])

        if a == 3 or a == 4:
            sample_gene_indices = tuple(sample(xrange(len(M[0])), self.gene_fraction))

            M = M.take(sample_gene_indices, 1)
        
        if self.norm_var:
            M = M / numpy.sqrt(M.var(0))
    
        return dataset, M

    def run_clustering(self):
        """Run clustering algorithms, grouped by type"""
        
        def run(alg, dataset, data_matrix, linkage = None):
            alg(dataset, data_matrix, self.num_clusters, self.distance_metric, linkage=linkage)
            self.upd_similarity_matrix()
            self._reset_clusters()          #This is so the similarity matrix doesn't have added values

        dataset, data_matrix = self._gen_dataset()

        for alg in self.clustering_algs:
            if alg is HierarchicalCluster:      #Got a better way?
                for linkage in self.linkages:
                    run(alg, dataset, data_matrix, linkage)
            else:
                run(alg, dataset, data_matrix)

    def upd_similarity_matrix(self):
        """Generate a similarity matrix from each new clustering algorithm results"""

        num_samples = len(self.datapoints)
        datapoints = self.datapoints
        
        clustcount, totalcount = self.sim_matrix_clustcount, self.sim_matrix_totalcount

        for i in xrange(num_samples):
            for j in xrange(1, num_samples - i):
                k, m = i, i+j
                k_id, m_id = datapoints[k].cluster_id, datapoints[m].cluster_id

                if not (k_id is None or m_id is None):
                    if k_id == m_id:
                        clustcount[k][m] += 1
                    
                    totalcount[k][m] += 1

    @only_once
    def gen_consensus_matrix(self, clustcount_matrices, totalcount_matrices):
        """Create a consensus matrix based on similarity matrices"""

        final_matrix_clustcount = sum(clustcount_matrices)
        final_matrix_totalcount = sum(totalcount_matrices)
        
        num_samples = len(self.datapoints)
        consensus_matrix = self.consensus_matrix

        thresh = self.matrix_thresh #Values may not be lower than this before being set to 0

        for i in xrange(num_samples):
            for j in xrange(1, num_samples - i):
                k, m = i, i+j

                if final_matrix_totalcount[k][m]:
                    consensus_matrix[k][m] = final_matrix_clustcount[k][m] / final_matrix_totalcount[k][m]

                    if consensus_matrix[k][m] < thresh:
                        consensus_matrix[k][m] = 0.0

        return consensus_matrix + consensus_matrix.transpose()

    @only_once
    def hcluster_consensus(self):
        """Cluster the data using the consensus matrix as a distance metric"""

        data_matrix = numpy.array([ x.data for x in self.datapoints ])

        if self.final_alg == 'Hierarchical':
            self.tree = HierarchicalCluster(self.datapoints, data_matrix, self.num_clusters, 
                                            self.distance_metric, linkage='average', distance_matrix=(1 - self.consensus_matrix)).tree
        elif self.final_alg == 'PAM':
            PAMCluster(self.datapoints, data_matrix, self.num_clusters, self.distance_metric, distance_matrix = (1 - self.consensus_matrix))
        else:
            self.final_alg(self.datapoints, data_matrix, self.num_clusters, self.distance_metric, distance_matrix = (1 - self.consensus_matrix))
    
    @only_once
    def reorder_consensus(self):
        """
        Use simulated annealing to reorder the consensus matrix in a way that maximises the similarity between
        close indices and maximises the dissimilarity between distant ones.  Once this function finishes,
        ConsensusCluster.tree.sequence will contain the optimal ordering, and consensus_matrix will be reordered
        in this manner.
        
        NOTE: I'm well aware this is an extensive amount of code duplication.  I've come to terms with it.
        
        """
        
        print "\n\nReordering the consensus matrix...\n"

        if self.tree is not None:

            treetype.reorder(self.tree, self.consensus_matrix)    
            best_order = tuple(self.tree.sequence)
            self.reorder_indices = self.tree.sequence

        else:
            sample_len = len(self.datapoints)
            sample_order = list(numpy.array([ x.cluster_id for x in self.datapoints ]).argsort()) #SA is much faster if you give it a good start
    
            temp = 0.5
     
            #Local funcs
            rand_idx, e, ran = random.randint, math.e, random.random
             
            try:
                import sa
                energy = sa.c_energy
            except:
                print "WARNING: No SA C-extension found! SA will be very slow!"
                cost        = lambda i, j, matrix: matrix[i][j]      #The similarity between two samples
                energy      = lambda x, matrix: sum([ cost(x[i], x[i+1], matrix) for i in range(sample_len - 1) ])**2  #Sum of the cost of each successive pair, squared
    
            not_accepted, last_best, new_energy = 0, 0, energy(sample_order, self.consensus_matrix)
            best_energy, best_order = new_energy, list(sample_order)
            
            print "Starting energy score:", new_energy
    
            for i in xrange(1, 4000000):
    
                last_energy = energy(sample_order, self.consensus_matrix)
                last_order = list(sample_order)
    
                a, b = rand_idx(0, sample_len - 1), rand_idx(0, sample_len - 1)
                while (a == b):
                    a, b = rand_idx(0, sample_len - 1), rand_idx(0, sample_len - 1)
    
                if a < b:
                    sample_order.insert(a, sample_order.pop(b))         #Random insertion
                else:
                    sample_order.insert(b, sample_order.pop(a))
    
                new_energy = energy(sample_order, self.consensus_matrix)
    
                if not (i % 2000) and i < 25000:                        #Ramp up temperature
                    if ((i - not_accepted) / float(i)) < 0.1:
                        temp += 1
    
                if not (i % 25000):
                    temp = temp * 0.90
                    print "Acceptance rate:", ((i - not_accepted) / float(i))
    
                if new_energy < last_energy:
                    if ran() > e**((new_energy - last_energy) / temp):
                        sample_order = last_order       #Don't accept
                        not_accepted += 1
    
                elif new_energy > best_energy:
                    best_energy = new_energy
                    best_order = list(sample_order)
                    #print "New best energy %f at %d, %d since the last" % (best_energy, i, (i - last_best))
                    last_best = i
    
                if (i - last_best) > 100000:            #No point in going farther than this, usually
                    print "Breaking at", i
                    break
    
            print "\nFinal energy score:", best_energy

            self.reorder_indices = best_order #Use this to generate the logs afterwards
            best_order = tuple(best_order)

        #Order both rows and columns using optimal order
        self.consensus_matrix = self.consensus_matrix.take(best_order,1).transpose().take(best_order,1)

    def _reset_clusters(self):
        """Ensure the similarity matrix makes sense"""

        datapoints = self.datapoints

        for i in range(len(datapoints)):
            datapoints[i].cluster_id = None