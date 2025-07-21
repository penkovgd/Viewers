import { DicomMetadataStore, utils } from '@ohif/core';

export default function getCommandsModule({ servicesManager, commandsManager, extensionManager }) {
  const { displaySetService, measurementService } = servicesManager.services;
  const actions = {
    sendMeasurments: async () => {
      const { filterTool } = utils.MeasurementFilters;
      const measurementData = measurementService.getMeasurements(filterTool('Probe'));
      console.log('Got measurments:', measurementData);

      // Для скорости тестирования убрал эту проверку
      // if (measurementData.length < 2) {
      // throw new Error('At least 2 points required');
      // console.error('At least 2 points required');
      // return;
      // }

      // Проверяем, чтобы у всех measurements был одинаковый StudyUID и SeriesUID
      const studyUIDs = new Set(measurementData.map(m => m.referenceStudyUID));
      const seriesUIDs = new Set(measurementData.map(m => m.referenceSeriesUID));

      if (studyUIDs.size !== 1) {
        throw new Error(`Inconsistent referenceStudyUID values: ${[...studyUIDs].join(', ')}`);
      }
      if (seriesUIDs.size !== 1) {
        throw new Error(`Inconsistent referenceSeriesUID values: ${[...seriesUIDs].join(', ')}`);
      }

      const [StudyInstanceUID] = studyUIDs;
      const [SeriesInstanceUID] = seriesUIDs;

      // const StudyInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019';
      // const SeriesInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810150182600001696'; // малленкая серия (1 инстанс)
      // const SeriesInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810501260100009281'; // большая серия (800 инстансов)
      // const SeriesInstanceUID = '1.3.12.2.1107.5.8.15.133421.30000024122816392585900000071'; // MIP Range
      const dataSource = extensionManager.getActiveDataSource()[0];
      const series = await dataSource.retrieve.series.metadata({ StudyInstanceUID });
      const SeriesRetrieveURL = series.find(
        s => s.SeriesInstanceUID === SeriesInstanceUID
      ).RetrieveURL;
      console.log(SeriesRetrieveURL); // http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019/series/1.3.12.2.1107.5.1.4.76270.30000024122810501260100009281?accept=application/zip

      try {
        // Получаем zip
        const zipResponse = await fetch(SeriesRetrieveURL + '?accept=application/zip', {
          method: 'GET',
          headers: {
            Accept: 'application/zip',
          },
        });
        if (!zipResponse.ok) {
          throw new Error(`DICOM fetch error: ${zipResponse.status} ${zipResponse.statusText}`);
        }

        const zipBlob = await zipResponse.blob();

        const formData = new FormData();

        // Добавляем zip в тело запроса
        formData.append('file', zipBlob, 'series.zip');

        // Добавляем точки в тело запроса
        formData.append('measurements', JSON.stringify(measurementData));

        // https://httpbin.org/post
        // http://127.0.0.1:8000/generate_mpr/
        const response = await fetch('http://127.0.0.1:8000/reconstruct', {
          method: 'POST',
          body: formData,
        });
        if (!response.ok) {
          throw new Error(`Backend error: ${response.status} ${response.statusText}`);
        }

        const promiseId = 'DCM4CHEE:' + StudyInstanceUID; // пересмотреть
        dataSource.deleteStudyMetadataPromise(promiseId);

        // Сохраняем .dcm от бекенда
        const arrayBuffer = await response.arrayBuffer();
        await dataSource.store.dicom(arrayBuffer); // ничего не возвращает, к сожалению

        const series = await dataSource.retrieve.series.metadata({ StudyInstanceUID });
        console.log('ok');
      } catch (error) {
        console.error('Fetch operation failed:', error);
      }

      // DicomMetadataStore.addInstances(series);
      // const series = await dataSource.query.series.search(StudyInstanceUID);
      // DicomMetadataStore.addInstance(arrayBuffer);
      // console.log('ok');

      // Через filesToStudies
      // const blob = await response.blob();
      // const res = await filesToStudies([blob]);
      // console.log('ok');

      // const displaySets = displaySetService.getActiveDisplaySets();
      // for (const ds of displaySets) {
      //   displaySetService.setDisplaySetMetadataInvalidated(ds.displaySetInstanceUID);
      // }

      // // Получаем метаданные study от DicomMetadataStore
      // const studyMetadata = DicomMetadataStore.getStudy(StudyInstanceUID);
      // console.log('Study metada from DicomMetadataStore:', studyMetadata);

      // // Получаем метаданные от dataSource

      // Фетчим новые series
      // const dataSource = extensionManager.getActiveDataSource()[0];
      // console.log('datasource', dataSource);
      // // current study qido
      // const qidoForStudyUID = await dataSource.query.series.search(
      //   '1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019'
      // );

      // const study_1 = DicomMetadataStore.getStudy(StudyInstanceUID);
      // DicomMetadataStore.addStudy('1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019');
      // DicomMetadataStore.addInstances([{ StudyInstanceUID, SeriesInstanceUID }], true);
      // const study_2 = DicomMetadataStore.getStudy(
      //   '1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019'
      // );
      // console.log(study_1);

      // try to fetch the prior studies based on the patientID if the
      // server can respond.
      // const mrn = qidoForStudyUID[0].mrn;

      // await dataSource.query.studies.search({
      //   patientId: mrn,
      //   disableWildcard: true,
      // });

      // const seriesMetadata = await dataSource.retrieve.series.metadata({ StudyInstanceUID });
      // console.log('Series Metadata from dataSource:', seriesMetadata);
    },
  };
  const definitions = {
    sendMeasurments: {
      commandFn: actions.sendMeasurments,
    },
  };
  return {
    actions,
    definitions,
    defaultContext: 'ROUTE:VIEWER',
  };
}
