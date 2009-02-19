"""

Default clustering workflow and associated front end


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

import warnings
warnings.simplefilter('ignore', DeprecationWarning)

import numpy, sys, time, os
import pca, parsers, cluster, display, scripts

from mpi_compat import *

try:
    import psyco
    psyco.full()
except:
    pass

try:
    import euclidean
    EUC_C_EXT_ENABLED = 1
except:
    EUC_C_EXT_ENABLED = 0

if display.GTK_ENABLED:
    import gtk, gobject

DEBUG = 1


class CommonCluster(object):
    """

    CommonCluster

        Common class

        This class presents a default workflow for Consensus Clustering.  It is designed to be subclassed to suit your needs.

        See individual methods for advice on appropriate subclassing methodology.

        Usage:
            
            class MyCluster(CommonCluster):

                def __init__(self, parser, filename, log2, sub_medians, center, scale, pca_fraction, eigenvector_weight,
                             kvalues, subsamples, subsample_fraction, norm_var, **kwds):
                    
                    #Some things
                    CommonCluster.__init__(self, parser, filename, ....

            Or simply CommonCluster(parser, filename, ....
            
            In either case, CommonCluster will be run with the following options:

                parser              - parsers.ParseX class, see parsers.py.  No default.
                filename            - File to be parsed by parser, see parsers.py.  No default.
                log2                - Take the log2 of all data.  Default: False
                sub_medians         - Subtract the median of sample medians from each entry in M.  Default: False
                center              - Normalise genes over all samples to have mean 0.  Default: True
                scale               - Normalise genes over all samples by dividing by the Root-Mean-Square.  Default: False
                pca_fraction        - Choose genes from those principle components that explain pca_fraction of the variance.  Default: 0.85
                eigenvector_weight  - Take the top eigenvector_weight fraction of genes that occur with high weights in selected components.  Default: 0.25
                kvalues             - List of K-Values to cluster.  Default: [2, 3, 4, 5, 6]
                subsamples          - Number of subsampling iterations to form consensus.  Default: 300
                subsample_fraction  - Fraction of samples/genes to cluster each subsample.  Default: 0.8
                norm_var            - Boolean variable.  If True, genes will be standardised to have variance 1 over all samples
                                      each clustering iteration.  Default: False

    """
    
    def __init__(self, parser, filename, log2=False, sub_medians=False, center=True, scale=False, pca_fraction=0.85, eigenvector_weight=0.25,
                 kvalues=range(2,7), subsamples=300, subsample_fraction=0.8, norm_var=False, keep_list=None, pca_only=False, pca_legend=True, **kwds):
        """
    
        Initialise clustering procedure and tell the user what's going on.
    
        If you need to subclass __init__, make sure you call CommonCluster.__init__(self, parser, filename, **kwds), where kwds is a dict of any
        options for which the default is insufficient.  Calling __init__ will in turn call all parsing/pca/clustering methods.
    
        Don't worry if MPI fails.  It's supposed to if you aren't using it.
    
        """

        if not hasattr(self, 'console'):
            self.console = display.ConsoleDisplay(log=False)

        #Files containing lists of sample_ids to keep, undocumented...
        if keep_list is None:
            if len(sys.argv) == 1:
                self.keep_list = None
            else:
                self.keep_list = sys.argv[1:] #Really needs to get put in a set of command line options at some point
        else:
            self.keep_list = keep_list

        console = self.console
    
        try:

            if parser is None or filename is None:
                console.except_to_console('No parser or no filename selected!')
    
            self.sdata = console.announce_wrap('Parsing data...', parser, filename)
    
            if self.keep_list is not None:
                self.sdata, self.defined_clusters = console.announce_wrap('Removing samples not found in %s...' % ", ".join(self.keep_list), scripts.scale_to_set, self.sdata, self.keep_list)
    
            console.announce_wrap('Preprocessing data...', self._preprocess)
    
            idlist = [ x.sample_id for x in self.sdata.samples ]
            if len(dict.fromkeys(idlist)) != len(idlist):
                console.except_to_console('One or more Sample IDs are not unique!')
    
            console.announce_wrap('Running PCA...', self.run_pca, log2, sub_medians, center, scale, pca_fraction, eigenvector_weight, pca_legend)
            
            if not pca_only:
                console.announce_wrap('Postprocessing data...', self._postprocess)
        
                console.write("Using MPI?")
            
                if MPI_ENABLED:
                    console.success()
                else:
                    console.fail()
        
                for i in kvalues:
                    self.run_cluster(i, subsamples, subsample_fraction, norm_var, kwds)

        except:
            if DEBUG:
                raise
            else:
                pass

        self._complete_clustering(kwds)

    @only_once
    def makeplot(self, M, V, label, pca_legend=True):
        """
    
        Use matplotlib and display.py's Plot function to draw the samples along the first two Principle Components
    
        Usage: makeplot(sdata, V, label)
            
            sdata   - parsers.Parse object containing sample points and data in numpy.array form
            V       - The eigenvectors of the covariance matrix as determined by SVD
            label   - The filename will be of the form "label - timestamp.png"
    
        If matplotlib isn't installed, this function will simply do nothing.
    
        WARNING:    Depending on how the matrix is decomposed you may find different, but also correct, values of V
                    This will manifest itself as the same plot, but reflected in one or both directions
        
        """
    
        plots = []
        legend = []
    
        N = numpy.dot(V[:2], numpy.transpose(M))
    
        if hasattr(self, 'defined_clusters'):
            
            indices = {}
            sample_ids = [ x.sample_id for x in self.sdata.samples ]
            
            for cluster_id in self.defined_clusters:
                for sample_id in self.defined_clusters[cluster_id]:
                    indices.setdefault(cluster_id, []).append(sample_ids.index(sample_id))
        
            for cluster in indices:
                plot = N.take(tuple(indices[cluster]), 1)
        
                if plot.any():
                    plots.append(plot)
                    legend.append(cluster)

        else:
            #No kept files, just do as you're told
            legend = None
            plots = [N]     

        if not pca_legend:
            legend = None
    
        display.Plot(plots, legend = legend, fig_label = label)
    
    def run_pca(self, log2, sub_medians, center, scale, pca_fraction, eigenvector_weight, pca_legend=True):
        """
    
        Create a matrix from self.sdata.samples, normalise it, and then run PCA to reduce dimensionality.
    
        Usage: self.run_pca(log2, sub_medians, center, scale, pca_fraction, eigenvector_weight)
    
            log2                - Take the log2 of all data.
            sub_medians         - Subtract the median of sample medians from each entry in M.
            center              - Normalise genes over all samples to have mean 0.
            scale               - Normalise genes over all samples by dividing by the Root-Mean-Square.
            pca_fraction        - Choose genes from those principle components that explain pca_fraction of the variance.
            eigenvector_weight  - Take the top eigenvector_weight fraction of genes that occur with high weights in selected components.

        This function runs makeplot once the data has been normalised.
        A logfile called "PCA results - timestamp.log" will be created with PCA result information.

        Note:

            MPI compatibility has changed somewhat in recent times.  Now, in order to save memory, only rank 0 performs PCA while
            other nodes wait in sleep timers.  Once PCA has completed, the nodes are woken and the reduced data is broadcast.
    
        """

        def reduce(M, gene_indices):
            for i in xrange(len(self.sdata.samples)):
                self.sdata.samples[i].data = M[i]
        
            if hasattr(self.sdata, 'gene_names') and len(self.sdata.gene_names):
                self.sdata.gene_names = self.sdata.gene_names.take(gene_indices)

                console.new_logfile('PCA Results - Feature list')
                console.log("\nReliable features:\n", display=False)
                
                for name in self.sdata.gene_names:
                    console.log("%s" % name, display=False)
    
        console = self.console

        if MPI_ENABLED:
            sleep_nodes(2)

            if mpi.rank != 0:
                M, gene_indices = mpi.bcast()    #Block until we get the go-ahead from 0
                reduce(M, gene_indices)
                return
    
        console.new_logfile('PCA results')
        
        M = numpy.array([ x.data for x in self.sdata.samples ])
    
        console.log("Normalising %sx%s matrix" % (len(self.sdata.samples), len(self.sdata.samples[0].data)))
    
        avg = numpy.average(M, 0)   #We NEED to center for PCA to work, but the user may not want that.  So we save the value here and add it later.

        M = pca.normalise(M, log2=log2, sub_medians=False, center=True, scale=scale)
    
        #Unrolling pca.select_genes_by_pca...
        V = pca.pca(M, pca_fraction)    #From SVD
        gene_indices = pca.select_genes(V, eigenvector_weight)

        console.log("Found %s principle components in the top %s fraction" % (len(V), pca_fraction))
        console.log("Found %s reliable features occurring with high weight (top %s by absolute value)" % (len(gene_indices), eigenvector_weight))
        
        self.makeplot(M, V, 'PCA results - PC2v1 - All samples', pca_legend)
        self.makeplot(M, V[1:], 'PCA results - PC3v2 - All samples', pca_legend)
        
        if not center and not scale:
            M += avg    #De-center if the user doesn't want it
            
        if sub_medians:
            M = pca.normalise(M, log2=False, sub_medians=True, center=False, scale=False)
    
        #Reduce dimensions
        M = M.take(gene_indices, 1)

        if MPI_ENABLED:
            wake_nodes(2)
    
            if mpi.rank == 0:
                mpi.bcast((M, gene_indices))

        reduce(M, gene_indices)
    
    def run_cluster(self, num_clusters, subsamples, subsample_fraction, norm_var, kwds):
        """
    
        Run the clustering routines, generate a heatmap of the consensus matrix, and fill the logs with cluster information.
    
        Each time this is run it will create a logfile with the number of clusters and subsamples in its name.  This contains
        information on which samples where clustered together for that particular K value.
    
        Usage: self.run_cluster(num_clusters, subsamples, subsample_fraction, norm_var, kwds)
    
            num_clusters        - K value, or the number of clusters for the clustering functions to find for each subsample.
            subsamples          - The number of subsampling iterations to run.  In each subsample, the genes, samples, or both may
                                  be randomly selected for clustering.  This helps to ensure robust clustering.  More subsamples, more
                                  robust clusters.
            subsample_fraction  - The fraction of SNPs, samples, or both to take each subsample.  0.8 is a good default.
            norm_var            - Boolen variable.  If True, , genes will be standardised to have variance 1 over all samples
                                  each clustering iteration.
            kwds                - Additional options to be sent to cluster.ConsensusCluster
    
        It's probably a very bad idea to subclass run_cluster.  The _report and _save_hmap functions are almost certainly what you want.
    
        """
   
        console = self.console
        console.new_logfile(logname = '%s clusters - %s subsamples' % (num_clusters, subsamples))
        
        console.log("\nSamples: %s" % len(self.sdata.samples))
    
        console.write("\nClustering data...")
    
        if EUC_C_EXT_ENABLED:
            distance_metric = euclidean.euclidean
        else:
            print "WARNING: No euclidean C-extension found!  Clustering will be very slow!"
            import distance
            distance_metric = distance.euclidean
    
        args = locals()
        del args['self']
        args.update(kwds)

        #Actual work
        clust_data = cluster.ConsensusCluster(self.sdata, **args)
        
        console.write("\n\nBuilding heatmap...")
        colour_map = self._save_hmap(clust_data, **args)
        
        console.write("Generating logfiles...")
        self._report(clust_data, colour_map=colour_map, **args)
    
        if display.HMAP_ENABLED:
            console.success()
        else:
            console.fail()
    
        #If we're repeating, this is a good idea
        clust_data._reset_clusters()

    @only_once
    def _report(self, clust_data, console, **kwds):
        """

        _report is called by run_cluster after each clustering set at a particular k-value is complete.

        Its job is to inform the user which clusters went where.  This can be done to the screen and to the logfile using console.log()

        Subclassing:

            @only_once
            def _report(self, clust_data, console, **kwds):

                etc...

            clust_data.datapoints is a list of SampleData objects, each of which has a cluster_id attribute.  This attribute indicates
            cluster identity, and any SampleData objects that share it are considered to be in the same cluster.  This doesn't have to be
            1, 2, 3...etc.  In fact, it doesn't have to be a number.

            See display.ConsoleDisplay for logging/display usage.

            You may want to subclass _report if you want to report on additional information, such as a signal-to-noise ratio test of gene
            expression between any two clusters.

        """

        #SNR Threshold
        threshold = 0.5
        
        #Initialise the various dictionaries
        colour_map = kwds['colour_map']

        if hasattr(self, 'defined_clusters'):
            sample_id_to_cluster_def = {}

            for cluster_def in self.defined_clusters:
                for sample_id in self.defined_clusters[cluster_def]:
                    sample_id_to_cluster_def[sample_id] = cluster_def

        cluster_sample_ids = dict()
        cluster_sample_indices = dict()
    
        for clust_obj in [ (clust_data.datapoints[x].sample_id, clust_data.datapoints[x].cluster_id, x) for x in clust_data.reorder_indices ]:
            sample_id, cluster_id, sample_idx = clust_obj

            cluster_sample_ids.setdefault(cluster_id, []).append(sample_id)
            cluster_sample_indices.setdefault(cluster_id, []).append(sample_idx)
    
        #Start writing the log
        console.log("\nClustering results")
        console.log("---------------------")
    
        console.log("\nNumber of clusters: %s\nNumber of subsamples clustered: %s\nFraction of samples/features used in subsample: %s" % (kwds['num_clusters'], kwds['subsamples'], kwds['subsample_fraction']))
        console.log("\n---------------------")
        console.log("\nClusters")

        cluster_list = list(enumerate(cluster_sample_ids)) #(num, cluster_id) pairs

        for cluster in cluster_list:
            cluster_num, cluster_id = cluster

            console.log("\nCluster %s (%s):\n" % (cluster_num, colour_map[cluster_id]))
    
            for sample_id in cluster_sample_ids[cluster_id]:
                if hasattr(self, 'defined_clusters'):
                    console.log("\t%s\t\t%s" % (sample_id, sample_id_to_cluster_def[sample_id]))
                else:
                    console.log("\t%s" % sample_id)

        M = numpy.array([ x.data for x in clust_data.datapoints ]) 
        
        buffer = []
        clsbuffer = []
        
        if hasattr(self.sdata, 'gene_names'):
            
            for i in xrange(len(cluster_list)):
                for j in xrange(1, len(cluster_list) - i):
                    clust1, clust2 = cluster_list[i], cluster_list[i+j] #Still num, id pairs

                    ratios = pca.snr(M, cluster_sample_indices[clust1[1]], cluster_sample_indices[clust2[1]], threshold)
                    
                    if ratios:
                        buffer.append("\nCluster %s vs %s:" % (clust1[0], clust2[0]))
                        buffer.append("--------------------\n")
                        buffer.append("Gene ID\t\tCluster %s Avg\tCluster %s Avg\tSNR Ratio" % (clust1[0], clust2[0]))
    
                        for result in ratios:
                            buffer.append("%10s\t%f\t%f\t%f" % (self.sdata.gene_names[result[1]], result[2], result[3], result[0]))

                    if kwds.has_key('classifier') and kwds['classifier'] and ratios:
                        clsbuffer.append("\nCluster %s vs %s:" % (clust1[0], clust2[0]))
                        clsbuffer.append("--------------------\n")

                        classif_list = pca.binary_classifier(M, cluster_sample_indices[clust1[1]], cluster_sample_indices[clust2[1]], threshold)
                        #Returns (a, b), where a is w in (wi, i) pairs and b is w0
                        clsbuffer.append("w0 is %s" % classif_list[1])
                        clsbuffer.append("\nGene ID\t\tMultiplier")

                        for result in classif_list[0]:
                            clsbuffer.append("%10s\t%f" % (self.sdata.gene_names[result[1]], result[0]))
        
        def write_buffer(name, desc, buf):
            console.new_logfile(name)
            console.log(desc, display=False)

            for line in buf:
                console.log(line, display=False)

        if buffer:
            write_buffer('SNR Results - %s clusters - %s subsamples' % (kwds['num_clusters'], kwds['subsamples']), "SNR-ranked features with ratio greater than %s" % threshold, buffer)

        if clsbuffer:
            write_buffer('Binary Classifier - %s clusters - %s subsamples' % (kwds['num_clusters'], kwds['subsamples']), "Based on SNR-ranked features with ratio greater than %s" % threshold, clsbuffer)
    
    @only_once
    def _save_hmap(self, clust_data, **kwds):
        """

        _save_hmap uses display.Clustmap to produce a heatmap/dendrogram of the consensus matrix produced by cluster.ConsensusCluster

        Subclassing:

            @only_once
            def _save_hmap(self, clust_data, **kwds):

                etc

            Really, the best reason to subclass _save_hmap is to change the heatmap labels.  See display.Clustmap for additional syntax.

            example: display.Clustmap(clust_data, [ clust_data.datapoints[x].sample_class for x in clust_data.reorder_indices ]).save('Consensus Matrix')

                ...will create a file called Consensus Matrix.png, which contains the consensus matrix heatmap labeled by sdata.samples[x].sample_class.

            clust_data.reorder_indices is (predictably) a list of indices which constitute the best order.  Since cluster.ConsensusCluster
            reorders the consensus matrix (clust_data.consensus_matrix) for you (but doesn't touch sdata.samples/clust_data.datapoints), you'll
            need to reorder the label list accordingly.  This can be just a list of labels as well, though once again you'll have to reorder your list
            to match reorder_indices.  A list comprehension of the general form [ labels[x] for x in clust_data.reorder_indices ] will do this for you,
            assuming labels is in the same order as sdata.samples/clust_data.datapoints.

            display.Clustmap.save() creates an image file and saves it to disk.
            display.Clustmap.show() opens a GTK window with the image.  Requires GTK.  See display.py.

        """

        filename = lambda s: "%s - %s clusters - %s subsamples" % (s, kwds['num_clusters'], kwds['subsamples'])

        if clust_data.datapoints[0].sample_class is not None:
            labels = [ " - ".join([str(clust_data.datapoints[x].sample_id), str(clust_data.datapoints[x].sample_class)]) for x in clust_data.reorder_indices ]
        else:
            labels = [ clust_data.datapoints[x].sample_id for x in clust_data.reorder_indices ]

        map = display.Clustmap(clust_data, labels)
        map.save(filename('Consensus Matrix'))

        return map.colour_map

    def _preprocess(self):
        """

        Any data preprocessing that needs to be done BEFORE PCA should be done by subclassing this method

        Subclassing:

            def _preprocess(self):

                etc

        _preprocess shouldn't return anything, so any preprocessing should be done by extracting self.sdata.sample[x].data objects and
        putting them back when you're done.

        example: Take sequence data found by parser and convert it into a binary agreement matrix by comparing it to some reference
                 sequence
        
        This method does nothing on its own.

        """

        pass

    def _postprocess(self):
        """

        Any data postprocessing that needs to be done AFTER PCA but BEFORE CLUSTERING should be done by subclassing this method

        Subclassing:

            def _postprocess(self):

                etc

        _postprocess shouldn't return anything, so any postprocessing should be done by extracting self.sdata.sample[x].data objects and
        putting them back when you're done.

        example: Choose a random subset of the data to cluster, rather than the entire set

        This method does nothing on its own.

        """

        pass

    def _complete_clustering(self, kwds):
        """

        Run when the clustering finishes.

        Right now it just ungreys the button and resets graphical things.

        """

        if hasattr(self, 'sdata'):
            del self.sdata  #Safe side.

        if isinstance(self, Gtk_UI) and not (kwds.has_key('use_gtk') and not kwds['use_gtk']):

            if hasattr(self, 'startbutton'):
                self.startbutton.set_sensitive(True)

            self.mpi_wait_for_start()


class Gtk_UI(CommonCluster):
    """

    Gtk_UI

        GTK front end to CommonCluster.  All arguments and keywords are the same.  See CommonCluster for details.

        In order to run the GUI with a class already subclassing CommonCluster, simply subclass Gtk_UI instead:

        class MyCluster(Gtk_UI):

            def __init__(self, *args, **kwds):

                Gtk_UI.__init__(self, *args, **kwds)

        See CommonCluster for arguments.

        All display.ConsoleDisplay output will be placed in a GTK TextView instance instead.

        If GTK or display initialisation fails, Gtk_UI will behave as if CommonCluster was called instead.

    """

    def __init__(self, *args, **kwds):

        self.filename = None
        self.parser = None
        self.thread = None

        if not display.DISPLAY_ENABLED or (kwds.has_key('use_gtk') and not kwds['use_gtk']):
            CommonCluster.__init__(self, *args, **kwds)

        else:
            gtk.gdk.threads_init()
            gobject.threads_init()
            
            self.load_display(*args, **kwds)

            self.mpi_wait_for_start()

    
    def mpi_wait_for_start(self):
        """Tells the other nodes to sleep until Begin Clustering is pressed"""

        if MPI_ENABLED:
            sleep_nodes(1)

            if mpi.rank != 0:
                t_args = mpi.bcast()    #Block until we get the go-ahead from 0

                if t_args is not None:
                    thread_watcher(CommonCluster.__init__, (self, t_args[0], t_args[1]), t_args[2])

    @only_once
    def load_display(self, *args, **kwds):
            
        #Window Settings
        window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        window.connect("destroy", self.destroy)
        window.set_size_request(800, 600)
        window.set_resizable(False)

        #Boxen
        vbackbone = gtk.VBox(False)
        hbackbone = gtk.HBox(False)
        window.add(vbackbone)

        main_lvbox = gtk.VBox(False)
        main_rvbox = gtk.VBox(False)
        set_lvbox  = gtk.VBox(False)
        set_rvbox  = gtk.VBox(False)
        set_hbox   = gtk.HBox(False)

        hbackbone.pack_start(main_lvbox, True, True, 10)
        hbackbone.pack_end(main_rvbox, False, False, 10)

        #Tabs
        tabholder = gtk.HBox(False)
        tabs = gtk.Notebook()
        tabs.append_page(hbackbone, gtk.Label('Cluster'))
        tabs.append_page(set_hbox,  gtk.Label('Settings'))
        tabholder.pack_start(tabs, True, True, 10)

        #Menubar
        ui_str =    """
                    <ui>
                        <menubar name='Bar'>
                            <menu action='File'>
                                <menuitem action='Open'/>
                                <menuitem action='Quit'/>
                            </menu>
                            <menu action='Clustering'>
                                <menuitem action='Define Clusters'/>
                            </menu>
                        </menubar>
                    </ui>
                    
                    """

        uim = gtk.UIManager()
        window.add_accel_group(uim.get_accel_group())

        actgroup = gtk.ActionGroup('Cluster Menubar')
        actgroup.add_actions([ ('File', None, '_File'), ('Quit', gtk.STOCK_QUIT, '_Quit', None, 'Quits', self.destroy),
                               ('Open', gtk.STOCK_OPEN, '_Open File', None, 'Open a datafile', self.get_filename),
                               ('Clustering', None, '_Clustering'),
                               ('Define Clusters', None, '_Define Clusters', None, 'Set groups in a dataset from file', self.keep_list_dialog) ])

        uim.insert_action_group(actgroup, 0)
        uim.add_ui_from_string(ui_str)

        vbackbone.pack_start(uim.get_widget('/Bar'), False, False)
        vbackbone.pack_end(tabholder, True, True, 10)

        #Main Tab Stuff
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)

        textview = gtk.TextView()
        textview.set_editable(False)
        sw.add(textview)

        self.console = display.ConsoleDisplay(log=False, tview=textview)
        
        self.progress = gtk.ProgressBar()
        self.pbar_timer = gobject.timeout_add(100, self._upd_pbar)

        main_lvbox.pack_start(sw, True, True, 10)
        main_lvbox.pack_end(self.progress, False, False, 10)

        self.startbutton = gtk.Button('Begin Clustering')
        self.startbutton.connect('clicked', self.run_clustering)

        quitbutton = gtk.Button('Quit')
        quitbutton.connect('clicked', self.destroy)

        label = gtk.Label("Consensus Cluster\n\nMichael Seiler\nRutgers University")
        label.set_justify(gtk.JUSTIFY_CENTER)

        for obj in (self.startbutton, quitbutton):
            main_rvbox.pack_start(obj, False, False, 10)

        main_rvbox.pack_end(label, True, True, 10)

        #Settings Tab
        
        #Fabulous frame-filling functions
        def framepack(box, framelst):
            for frame in framelst:
                box.pack_start(frame, True, True, 10)

        def packbox(box, lst):
            for obj in lst:
                box.pack_start(obj, True, False, 4)

        def setentrywidths(width, lst):
            for obj in lst:
                obj.set_width_chars(width)
                obj.set_max_length(width)

        def labelbox(box, label=None):
            if label is None: return box
            v = gtk.VBox(False)
            v.pack_start(gtk.Label(label), False, False, 4)
            v.pack_start(box, False, False, 4)
            return v

        def newboxen(frame, label1=None, label2=None):
            v, h, h2 = gtk.VBox(False), gtk.HBox(False), gtk.HBox(False)
            v.pack_start(labelbox(h, label1), True, False, 5)
            v.pack_end(labelbox(h2, label2), True, False, 5)
            frame.add(v)
            return v, h, h2

        #Frames
        algsframe = gtk.Frame()
        genframe  = gtk.Frame()
        pcaframe  = gtk.Frame()
        miscframe = gtk.Frame()
        
        for frame in ((algsframe, 'Algorithm'), (genframe, 'General'), (pcaframe, 'PCA'), (miscframe, 'Misc')):
            frame[0].set_label(frame[1])
        
        framepack(set_lvbox, (genframe, algsframe))
        framepack(set_rvbox, (pcaframe, miscframe))
        framepack(set_hbox, (set_lvbox, set_rvbox))

        #Genframe
        vbox, hbox, h2box = newboxen(genframe)

        self.k_min, self.k_max = gtk.Entry(), gtk.Entry()
        self.subs_entry, self.sub_frac_entry = gtk.Entry(), gtk.Entry()

        setentrywidths(2, (self.k_min, self.k_max))
        setentrywidths(4, (self.subs_entry, self.sub_frac_entry))

        packbox(hbox, (gtk.Label('K-Value Range'), self.k_min, gtk.Label('to'), self.k_max))
        packbox(h2box, (labelbox(self.subs_entry, 'Subsamples'), labelbox(self.sub_frac_entry, 'Fraction to Sample')))

        #Algsframe
        vbox, alg_hbox, h2box = newboxen(algsframe, 'Cluster Using')
        
        link_hbox  = gtk.HBox(False)
        vbox.pack_start(labelbox(link_hbox, 'Linkages'), True, False, 5)

        self.kmeanbox    = gtk.CheckButton(label='K-Means')
        self.sombox      = gtk.CheckButton(label='SOM')
        self.pambox      = gtk.CheckButton(label='PAM')
        self.hierbox     = gtk.CheckButton(label='Hierarchical')

        self.singlebox   = gtk.CheckButton(label='Single')
        self.averagebox  = gtk.CheckButton(label='Average')
        self.completebox = gtk.CheckButton(label='Complete')

        packbox(alg_hbox, (self.kmeanbox, self.sombox, self.pambox, self.hierbox))
        packbox(link_hbox, (self.singlebox, self.averagebox, self.completebox))

        self.finalbutton, self.distbutton = gtk.combo_box_new_text(), gtk.combo_box_new_text()
        
        for text in ('Hierarchical', 'PAM'):
            self.finalbutton.append_text(text)

        for text in ('Euclidean', 'Pearson'):
            self.distbutton.append_text(text)

        packbox(h2box, (labelbox(self.finalbutton, 'Cluster Consensus Using'), labelbox(self.distbutton, 'Distance Metric')))

        #Pcaframe
        vbox, hbox, h2box = newboxen(pcaframe, 'Normalisation')

        self.log2box     = gtk.CheckButton(label='Log2')
        self.submedbox   = gtk.CheckButton(label='Sub Medians')
        self.centerbox   = gtk.CheckButton(label='Center')
        self.scalebox    = gtk.CheckButton(label='Scale')

        self.pca_frac_entry, self.eig_weight_entry = gtk.Entry(), gtk.Entry()
        setentrywidths(4, (self.pca_frac_entry, self.eig_weight_entry))

        packbox(hbox, (self.log2box, self.submedbox, self.centerbox, self.scalebox))
        packbox(h2box, (labelbox(self.pca_frac_entry, 'PCA Fraction'), labelbox(self.eig_weight_entry, 'Eigenvalue Weight')))

        #Miscframe
        vbox, hbox, h2box = newboxen(miscframe)

        self.normvarbox = gtk.CheckButton('Set Variance to 1')
        packbox(hbox, [self.normvarbox])

        #Defaults and convenience dict for accessing values
        self.clus_alg_widgets = dict([(self.kmeanbox, cluster.KMeansCluster), (self.sombox, cluster.SOMCluster), (self.pambox, cluster.PAMCluster),
                                      (self.hierbox, cluster.HierarchicalCluster)])

        self.linkage_widgets = dict([(self.singlebox, 'single'), (self.averagebox, 'average'), (self.completebox, 'complete')])

        #FIXME: You're so insensitive!
        self.distbutton.set_sensitive(False)

        #Monstrosity
        self.settings = {   'kvalues': lambda: range(int(self.k_min.get_text()), int(self.k_max.get_text()) + 1),
                            'subsamples': lambda: int(self.subs_entry.get_text()),
                            'subsample_fraction': lambda: float(self.sub_frac_entry.get_text()),
                            'clustering_algs': lambda: [ self.clus_alg_widgets[x] for x in self.clus_alg_widgets if x.get_active() ],
                            'linkages': lambda: [ self.linkage_widgets[x] for x in self.linkage_widgets if x.get_active() ],
                            'final_alg': lambda: self.finalbutton.get_model()[self.finalbutton.get_active()][0],
                            'log2': self.log2box.get_active,
                            'sub_medians': self.submedbox.get_active,
                            'center': self.centerbox.get_active,
                            'scale': self.scalebox.get_active,
                            'pca_fraction': lambda: float(self.pca_frac_entry.get_text()),
                            'eigenvector_weight': lambda: float(self.eig_weight_entry.get_text()),
                            'norm_var': self.normvarbox.get_active,
                            'keep_list': lambda: self.keep_list }
        
        self._set_defaults(args, kwds)

        window.show_all()
        
        gtk.gdk.threads_enter()
        gtk.main()
        gtk.gdk.threads_leave()

    @only_once
    def run_clustering(self, w, e=None):
        
        self.startbutton.set_sensitive(False)

        args = {}

        for setting in self.settings: #So only arguments from self.settings go to cluster...
            args[setting] = self.settings[setting]()

        if MPI_ENABLED:
            wake_nodes(1)
            
            if mpi.rank == 0:
                mpi.bcast((self.parser, self.filename, args))

        self.thread = Thread(target=CommonCluster.__init__, args=(self, self.parser, self.filename), kwargs=args)
        self.thread.start()

    @only_once
    def destroy(self, w):

        if MPI_ENABLED:
    
            if mpi.rank == 0:
                if self.thread is None:
                    wake_nodes(1)
                    mpi.bcast(None)
                else:
                    wake_nodes(3)

        gobject.source_remove(self.pbar_timer)

        gtk.main_quit()

    @only_once
    def get_filename(self, w):

        def set_filename(w):
            self.filename = box.get_filename()
            self.parser = getattr(parsers, 'Parse' + parser_lst[button.get_active()])

            box.destroy()
            Thread(target = self._announce_fileparser).start()

        parser_lst = []

        #Get the names
        for key in parsers.__dict__:
            if key.find('Parse') == 0:
                pname = key[5:]

                if pname == 'Normal':           #Pretty sleazy way of hardcoding default
                    parser_lst.insert(0, pname)
                else:
                    parser_lst.append(pname)

        box = gtk.FileSelection("Select file")
        box.ok_button.connect("clicked", set_filename)
        box.cancel_button.connect("clicked", lambda w: box.destroy())
        box.set_resizable(False)

        button = gtk.combo_box_new_text()
        for text in parser_lst:
            button.append_text(text)

        button.set_active(0)
        
        parserbox = gtk.HBox(False)
        buttonlabel = gtk.Label('Select a Parser:')
        for obj in (buttonlabel, button):
            parserbox.pack_start(obj)

        box.action_area.pack_start(parserbox)

        box.show_all()

    @only_once
    def keep_list_dialog(self, w):

        chooser = gtk.FileChooserDialog('Open..', None, gtk.FILE_CHOOSER_ACTION_OPEN,
                                       (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))

        chooser.set_select_multiple(True)
        chooser.set_default_response(gtk.RESPONSE_OK)
        chooser.set_size_request(640,480)

        filter = gtk.FileFilter()
        filter.set_name("All Files")
        filter.add_pattern("*")
        chooser.add_filter(filter)

        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            self.keep_list = chooser.get_filenames()

        chooser.destroy()

        if self.keep_list is not None:
            Thread(target=self._announce_keep_list).start()

    def _set_defaults(self, args, kwds):

        #Things that aren't widgets
        self.keep_list = None

        #Widgety things
        if args and args[0] is not None and args[1] is not None:
            self.parser = args[0]
            self.filename = args[1]
            self._announce_fileparser()
        else:
            self.console.write('Welcome to ConsensusCluster!  Please select a file for reading.')

        clus_widget_algs = dict([ (v,k) for (k,v) in self.clus_alg_widgets.iteritems() ])
        widget_linkages  = dict([ (v,k) for (k,v) in self.linkage_widgets.iteritems() ])

        def set_kvalue(lst):
            self.k_min.set_text(str(lst[0]))
            self.k_max.set_text(str(lst[-1]))

        def set_clus(lst):
            for alg in lst:
                clus_widget_algs[alg].set_active(1)

        def set_link(lst):
            for lnk in lst:
                widget_linkages[lnk].set_active(1)

        set_widgets = {     'kvalues': set_kvalue,
                            'subsamples': lambda s: self.subs_entry.set_text(str(s)),
                            'subsample_fraction': lambda s: self.sub_frac_entry.set_text(str(s)),
                            'clustering_algs': set_clus,
                            'linkages': set_link,
                            'final_alg': lambda s: self.finalbutton.set_active([ x[0] for x in self.finalbutton.get_model() ].index(s)),
                            'log2': self.log2box.set_active,
                            'sub_medians': self.submedbox.set_active,
                            'center': self.centerbox.set_active,
                            'scale': self.scalebox.set_active,
                            'pca_fraction': lambda s: self.pca_frac_entry.set_text(str(s)),
                            'eigenvector_weight': lambda s: self.eig_weight_entry.set_text(str(s)),
                            'norm_var': self.normvarbox.set_active }
    
        defaults = {        'kvalues': range(2,7),
                            'subsamples': 300,
                            'subsample_fraction': 0.8,
                            'clustering_algs': [ cluster.KMeansCluster ],
                            'linkages': [ 'average' ],
                            'final_alg': 'Hierarchical',
                            'log2': False,
                            'sub_medians': False,
                            'center': True,
                            'scale': False,
                            'pca_fraction': 0.85,
                            'eigenvector_weight': 0.25,
                            'norm_var': False }

        for key in defaults:
            if kwds.has_key(key):
                set_widgets[key](kwds[key])
            else:
                set_widgets[key](defaults[key])

        #FIXME: Why are you always hating on euclidean? Why?
        self.distbutton.set_active(0)
    
    def _upd_pbar(self):

        self.progress.set_fraction(self.console.progress_frac)

        return True

    def _announce_fileparser(self):

        self.console.write("File '%s' selected for reading, using %s" % (self.filename, self.parser.__name__))
        self.console.success()

    def _announce_keep_list(self):

        self.console.write("The sample ids in the following files are defined as clusters:")
        for file in self.keep_list:
            self.console.write(file)
        self.console.success()


if __name__ == '__main__':

    parser   = None
    filename = None

    args = {}

    Gtk_UI(parser, filename, **args)
